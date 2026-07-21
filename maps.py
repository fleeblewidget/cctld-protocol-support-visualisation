#!/usr/bin/env python3
"""
ccTLD Protocol Support Visualisation
Generates a choropleth map and small multiples from a technical profile CSV dataset.
"""

import pandas as pd
import geopandas as gpd
import plotly.express as px
import pycountry
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import sys
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = 'output'

# ccTLD label -> ISO 3166-1 alpha-2 exceptions
# Most ccTLDs map directly (label.upper() == ISO code) but these don't
ISO_EXCEPTIONS = {
    'uk': 'GB'  # ISO code for UK is GB
}

# TLDs to exclude from the map entirely (unassigned, regional, unused etc.)
# Note that .ac is in use at time of writing, but the visualisations use
# the larger .sh
EXCLUDE = {'eu', 'su', 'gb', 'ac'}

# Grouping rules - returns 0-5 for mapping to colours
# 5: DNSSEC + RDAP
# 4: RDAP only
# 3: DNSSEC + WHOIS
# 2: DNSSEC only
# 1: WHOIS only
# 0: no supported protocols

def group(row):
    ds    = row['ds']    == 'Y'
    rdap  = row['rdap']  == 'Y'
    whois = row['whois'] == 'Y'
    if ds and rdap:  return 5
    if rdap:         return 4
    if ds and whois: return 3
    if ds:           return 2
    if whois:        return 1
    return 0

def is_recommended(row):
    """True if DNSSEC is deployed with a RECOMMENDED signing algorithm"""
    return row['ds'] == 'Y' and row.get('ds_algorithm_status') == 'RECOMMENDED'

GROUP_LABELS = {
    5: 'DNSSEC + RDAP',
    4: 'RDAP, no DNSSEC',
    3: 'DNSSEC + WHOIS',
    2: 'DNSSEC only',
    1: 'WHOIS only',
    0: 'No support',
}

# Colour palette - red through amber to green
GROUP_COLOURS = {
    5: '#2a9d8f',
    4: '#8ecae6',
    3: '#e9c46a',
    2: '#f4a261',
    1: '#e76f51',
    0: '#e63946'
}

NO_DATA_COLOUR = '#cccccc'


# ---------------------------------------------------------------------------
# Data loading and preparation
# ---------------------------------------------------------------------------

def load_data(path):
    df = pd.read_csv(path)
    df['group'] = df.apply(group, axis=1)
    df['group_label'] = df['group'].map(GROUP_LABELS)

    # Build ISO code columns
    df['iso_a2'] = df.apply(
        lambda row: None if row['punycode_label'].startswith('xn--')
                    else label_to_iso(row['label']),
        axis=1
    )
    df['iso_a3'] = df['iso_a2'].apply(iso2_to_iso3)

    # Drop rows we can't map
    df = df[df['iso_a2'].notna()]

    print(f"Loaded {len(df)} ccTLDs")
    print("\nGroup distribution:")
    for s in sorted(GROUP_LABELS.keys(), reverse=True):
        count = (df['group'] == s).sum()
        print(f"  {s} - {GROUP_LABELS[s].replace(chr(10), ' ')}: {count}")

    return df


def label_to_iso(label):
    if label in EXCLUDE:
        return None
    if label in ISO_EXCEPTIONS:
        return ISO_EXCEPTIONS[label]
    return label.upper()

def iso2_to_iso3(iso2):
    if pd.isna(iso2):
        return None
    try:
        return pycountry.countries.get(alpha_2=iso2).alpha_3
    except AttributeError:
        return None


def load_world():
    world = gpd.read_file('sources/naturalearth_lowres/ne_50m_admin_0_countries.shp')
    # Fix known ISO code issues
    world.loc[world['NAME'] == 'France', 'ISO_A2'] = 'FR'
    world.loc[world['NAME'] == 'Norway', 'ISO_A2'] = 'NO'
    world.loc[world['NAME'] == 'Kosovo', 'ISO_A2'] = 'XK'
    # Rename column to match what we use downstream
    world = world.rename(columns={'ISO_A2': 'iso_a2'})
    return world


def merge_data(world, df):
    return world.merge(df, on='iso_a2', how='left')

# ---------------------------------------------------------------------------
# Interactive choropleth (Plotly) - hero map with overall groups
# ---------------------------------------------------------------------------

def make_interactive_map(df, output_path):
    # Plotly needs the group as a categorical for discrete colours
    df = df.copy()
    df['group_str'] = df['group'].astype(str)

    df['hover'] = (
        '<b>' + df['label'].str.upper() + '</b><br>' +
        df['country'] + '<br>' +
        'Group: ' + df['group'].astype(str) + '/5<br>' +
        df['group_label'].str.replace('\n', ' ') + '<br>' +
        'DNSSEC: ' + df['ds'] + '  |  ' +
        'RDAP: ' + df['rdap'] + '  |  ' +
        'WHOIS: ' + df['whois']
    )

    colour_map = {str(k): v for k, v in GROUP_COLOURS.items()}

    fig = px.choropleth(
        df,
        locations='iso_a3',
        color='group_str',
        color_discrete_map=colour_map,
        category_orders={'group_str': ['5', '4', '3', '2', '1', '0']},
        hover_name='country',
        custom_data=['hover'],
        title='ccTLD Technical Profiling — ' + pd.Timestamp.now().strftime('%B %Y'),
        labels={'group_str': 'Protocol Support'},
    )

    fig.update_traces(
        hovertemplate='%{customdata[0]}<extra></extra>'
    )

    fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor='white',
            showland=True,
            landcolor=NO_DATA_COLOUR,
            showocean=True,
            oceancolor='#f0f4f8',
            projection_type='natural earth',
        ),
        legend=dict(
            title='Protocol Support',
            orientation='v',
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor='white',
    )

    # Rename legend entries to be human readable
    for trace in fig.data:
        group_val = int(trace.name)
        trace.name = f"{trace.name} — {GROUP_LABELS[group_val].replace(chr(10), ' ')}"

    fig.write_html(output_path)
    print(f"Interactive map written to {output_path}")

# ---------------------------------------------------------------------------
# Static small multiples (matplotlib) - one map per metric
# ---------------------------------------------------------------------------

DNSSEC_ALGORITHM_COLOURS = {
    'RECOMMENDED':     '#2a9d8f',
    'MAY':             '#8ecae6',
    'NOT RECOMMENDED': '#e9c46a',
    'MUST NOT':        '#e63946',
    'n/a':             '#aaaaaa',  # no DNSSEC
}

def make_small_multiples(merged, output_path):
    # Binary metrics: (column, title, yes_colour, no_colour)
    # Multi-value metrics: (column, title, colour_map_dict, label_order)
    metrics = [
        {
            'type':      'multivalue',
            'col':       'ds_algorithm_status',
            'title':     'DNSSEC Algorithm Status',
            'colours':   DNSSEC_ALGORITHM_COLOURS,
            'order':     ['RECOMMENDED', 'MAY', 'NOT RECOMMENDED', 'MUST NOT', 'n/a'],
            'labels':    {
                'RECOMMENDED':     'Recommended algorithm',
                'MAY':             'Permitted algorithm',
                'NOT RECOMMENDED': 'Unrecommended algorithm',
                'MUST NOT':        'Unpermitted algorithm',
                'n/a':             'No DNSSEC',
            },
        },
        {
            'type':       'binary',
            'col':        'rdap',
            'title':      'RDAP',
            'yes_colour': '#2a9d8f',
            'no_colour':  '#e63946',
        },
        {
            'type':       'binary',
            'col':        'whois',
            'title':      'WHOIS',
            'yes_colour': '#2a9d8f',
            'no_colour':  '#e63946',
        },
    ]

    fig, axes = plt.subplots(1, 3, figsize=(24, 6))
    fig.suptitle(
        f'ccTLD Infrastructure by Protocol — {pd.Timestamp.now().strftime("%B %Y")}',
        fontsize=14,
        fontweight='bold',
        y=1.02
    )

    for ax, metric in zip(axes, metrics):
        if metric['type'] == 'binary':
            yes_colour = metric['yes_colour']
            no_colour  = metric['no_colour']

            def row_colour(row, yes=yes_colour, no=no_colour):
                val = row[metric['col']]
                if pd.isna(val):
                    return NO_DATA_COLOUR
                return yes if val == 'Y' else no

            colours = merged.apply(row_colour, axis=1)

            patches = [
                mpatches.Patch(color=yes_colour,     label='Yes'),
                mpatches.Patch(color=no_colour,      label='No'),
                mpatches.Patch(color=NO_DATA_COLOUR, label='No data'),
            ]

            yes_count = (merged[metric['col']] == 'Y').sum()
            total     = merged[metric['col']].notna().sum()
            annotation = f'{yes_count}/{total} ({yes_count/total*100:.0f}%)'

        else:  # multivalue
            colour_map = metric['colours']

            def row_colour(row, cmap=colour_map):
                val = row[metric['col']]
                return cmap.get(val, NO_DATA_COLOUR)

            colours = merged.apply(row_colour, axis=1)

            patches = [
                mpatches.Patch(
                    color=colour_map[status],
                    label=metric['labels'][status]
                )
                for status in metric['order']
            ]

            # Annotation: count of RECOMMENDED
            rec_count = (merged[metric['col']] == 'RECOMMENDED').sum()
            total     = (merged['ds'] == 'Y').sum()
            annotation = f'{rec_count}/{total} signed use recommended algorithm'

        merged.plot(ax=ax, color=colours, linewidth=0.3, edgecolor='white')
        ax.set_title(metric['title'], fontsize=11, fontweight='bold', pad=8)
        ax.axis('off')
        ax.legend(handles=patches, loc='lower left', fontsize=8, framealpha=0.8)
        ax.annotate(
            annotation,
            xy=(0.5, 0.02), xycoords='axes fraction',
            ha='center', fontsize=9, color='#444444',
        )

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Small multiples written to {output_path}")


# ---------------------------------------------------------------------------
# Static map (matplotlib)
# ---------------------------------------------------------------------------

def make_static_map(merged, output_path):
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))


    def row_colour(row):
        group_val = row.get('group')
        if pd.isna(group_val):
            return NO_DATA_COLOUR
        return GROUP_COLOURS.get(int(group_val), NO_DATA_COLOUR)

    colours = merged.apply(row_colour, axis=1)

    merged.plot(
        ax=ax,
        color=colours,
        linewidth=0.3,
        edgecolor='white',
    )

    ax.set_title(
        f'ccTLD Technical Profiling — {pd.Timestamp.now().strftime("%B %Y")}',
        fontsize=14, fontweight='bold', pad=12,
    )
    ax.axis('off')

    # Legend
    patches = [
        mpatches.Patch(color=GROUP_COLOURS[s], label=GROUP_LABELS[s].replace('\n', ' '))
        for s in sorted(GROUP_COLOURS.keys(), reverse=True)
    ]

    patches.append(mpatches.Patch(color=NO_DATA_COLOUR, label='No data / not assessed'))

    ax.legend(
        handles=patches,
        loc='lower left',
        fontsize=9,
        framealpha=0.9,
        title='Protocol Support',
        title_fontsize=9,
    )

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Static map written to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python visualise.py <results.csv>")
        print("  results.csv  Path to the ccTLD technical profile CSV generated by the data gathering scripts")
        sys.exit(1)

    csv_path = sys.argv[1]

    if not os.path.exists(csv_path):
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df     = load_data(csv_path)
    world  = load_world()
    merged = merge_data(world, df)

    make_interactive_map(df,     os.path.join(OUTPUT_DIR, 'profile_interactive.html'))
    make_static_map(merged, os.path.join(OUTPUT_DIR, 'profile_static.png'))
    make_small_multiples(merged,  os.path.join(OUTPUT_DIR, 'profile_multiples.png'))

    print("\nDone. Outputs:")
    print(f"  {OUTPUT_DIR}/profile_interactive.html  — embeddable interactive map")
    print(f"  {OUTPUT_DIR}/profile_static.png        — static consolidated protocol support map")
    print(f"  {OUTPUT_DIR}/profile_multiples.png     — detailed graphics by category")


if __name__ == '__main__':
    main()