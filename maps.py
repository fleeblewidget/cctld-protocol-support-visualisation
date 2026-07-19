#!/usr/bin/env python3
"""
ccTLD Maturity Visualisation
Generates a choropleth map and small multiples from a maturity CSV dataset.
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

# Scoring rules - returns 0-5
# 5: DNSSEC + RDAP          (all services)
# 4: RDAP only              (modern query layer, unsigned)
# 3: DNSSEC + WHOIS         (established, not modernised)
# 2: DNSSEC only            (secure, minimal interface)
# 1: WHOIS only             (legacy infrastructure)
# 0: nothing                (no detectable services)

def score(row):
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

SCORE_LABELS = {
    5: 'Full services\n(DNSSEC + RDAP)',
    4: 'RDAP, no DNSSEC',
    3: 'DNSSEC + WHOIS',
    2: 'DNSSEC only',
    1: 'WHOIS only',
    0: 'No infrastructure',
}

# Two shades per DNSSEC-positive band: recommended algorithm (darker), other (lighter)
# Scores 0 and 4 have no DNSSEC so only one shade needed
SCORE_COLOURS = {
    5: {'recommended': '#1a7a6e', 'other': '#2a9d8f'},
    4: {'recommended': '#8ecae6', 'other': '#8ecae6'},  # no DNSSEC, single shade
    3: {'recommended': '#c9a030', 'other': '#e9c46a'},
    2: {'recommended': '#d4803a', 'other': '#f4a261'},
    1: {'recommended': '#e76f51', 'other': '#e76f51'},  # no DNSSEC, single shade
    0: {'recommended': '#e63946', 'other': '#e63946'},  # no DNSSEC, single shade
}

# Scores where algorithm distinction applies (i.e. DNSSEC is present)
DNSSEC_SCORES = {2, 3, 5}

NO_DATA_COLOUR = '#cccccc'

def get_colour(row):
    """Return fill colour based on score and DNSSEC algorithm recommendation"""
    score_val = row.get('score')
    if pd.isna(score_val):
        return NO_DATA_COLOUR
    score_val = int(score_val)
    colours = SCORE_COLOURS.get(score_val, {'recommended': NO_DATA_COLOUR, 'other': NO_DATA_COLOUR})
    if score_val in DNSSEC_SCORES and is_recommended(row):
        return colours['recommended']
    return colours['other']

# ---------------------------------------------------------------------------
# Data loading and preparation
# ---------------------------------------------------------------------------

def load_data(path):
    df = pd.read_csv(path)
    df['score'] = df.apply(score, axis=1)
    df['score_label'] = df['score'].map(SCORE_LABELS)
    df['recommended'] = df.apply(is_recommended, axis=1)

    # Build ISO code columns - filter out IDNs
    df['iso_a2'] = df.apply(
        lambda row: None if row['punycode_label'].startswith('xn--')
                    else label_to_iso(row['label']),
        axis=1
    )
    df['iso_a3'] = df['iso_a2'].apply(iso2_to_iso3)

    # Drop rows we can't map
    df = df[df['iso_a2'].notna()]

    print(f"Loaded {len(df)} ccTLDs")
    print("\nScore distribution:")
    for s in sorted(SCORE_LABELS.keys(), reverse=True):
        count = (df['score'] == s).sum()
        if s in DNSSEC_SCORES:
            rec = ((df['score'] == s) & df['recommended']).sum()
            print(f"  {s} - {SCORE_LABELS[s].replace(chr(10), ' ')}: {count} "
                  f"({rec} recommended algorithm, {count - rec} other)")
        else:
            print(f"  {s} - {SCORE_LABELS[s].replace(chr(10), ' ')}: {count}")

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
    world.loc[world['NAME'] == 'France', 'ISO_A2'] = 'FR'
    world.loc[world['NAME'] == 'Norway', 'ISO_A2'] = 'NO'
    world.loc[world['NAME'] == 'Kosovo', 'ISO_A2'] = 'XK'
    world = world.rename(columns={'ISO_A2': 'iso_a2'})
    return world


def merge_data(world, df):
    return world.merge(df, on='iso_a2', how='left')

# ---------------------------------------------------------------------------
# Interactive choropleth (Plotly) - hero map with overall score
# ---------------------------------------------------------------------------

def make_interactive_map(df, output_path):
    df = df.copy()

    # Create a colour key combining score and recommendation status
    def colour_key(row):
        s = int(row['score'])
        if s in DNSSEC_SCORES and row['recommended']:
            return f"{s}_rec"
        return f"{s}_other"

    df['colour_key'] = df.apply(colour_key, axis=1)

    # Build colour map for all possible keys
    colour_map = {}
    for s, colours in SCORE_COLOURS.items():
        colour_map[f"{s}_rec"]   = colours['recommended']
        colour_map[f"{s}_other"] = colours['other']

    # Category order - recommended variants first within each score band
    category_order = []
    for s in [5, 4, 3, 2, 1, 0]:
        if s in DNSSEC_SCORES:
            category_order += [f"{s}_rec", f"{s}_other"]
        else:
            category_order.append(f"{s}_other")

    # Hover text
    df['hover'] = (
        '<b>' + df['label'].str.upper() + '</b><br>' +
        df['country'] + '<br>' +
        'Score: ' + df['score'].astype(str) + '/5 — ' +
        df['score_label'].str.replace('\n', ' ') + '<br>' +
        'DNSSEC: ' + df['ds'] + '  |  ' +
        'RDAP: '   + df['rdap'] + '  |  ' +
        'WHOIS: '  + df['whois'] + '<br>' +
        df.apply(lambda r: f"Algorithm: {r.get('ds_algorithm_name', 'N/A')} "
                           f"({r.get('ds_algorithm_status', 'N/A')})"
                           if r['ds'] == 'Y' else '', axis=1)
    )

    fig = px.choropleth(
        df,
        locations='iso_a3',
        color='colour_key',
        color_discrete_map=colour_map,
        category_orders={'colour_key': category_order},
        hover_name='country',
        custom_data=['hover'],
        title='ccTLD Technical Maturity — ' + pd.Timestamp.now().strftime('%B %Y'),
        labels={'colour_key': 'Maturity Score'},
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
            title='Maturity Score',
            orientation='v',
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor='white',
    )

    # Rename legend entries to be human readable
    for trace in fig.data:
        key = trace.name
        s = int(key.split('_')[0])
        rec = key.endswith('_rec')
        label = SCORE_LABELS[s].replace('\n', ' ')
        if s in DNSSEC_SCORES:
            trace.name = f"{label} ({'recommended' if rec else 'other'} algorithm)"
        else:
            trace.name = label

    fig.write_html(output_path)
    print(f"Interactive map written to {output_path}")

# ---------------------------------------------------------------------------
# Static small multiples (matplotlib) - one map per metric
# ---------------------------------------------------------------------------

def make_small_multiples(merged, output_path):
    metrics = [
        ('ds',    'DNSSEC (DS in root)', '#2a9d8f', '#e63946'),
        ('rdap',  'RDAP',                '#2a9d8f', '#e63946'),
        ('whois', 'WHOIS',               '#2a9d8f', '#e63946'),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(
        f'ccTLD Infrastructure by Protocol — {pd.Timestamp.now().strftime("%B %Y")}',
        fontsize=14,
        fontweight='bold',
        y=1.02
    )

    for ax, (col, title, yes_colour, no_colour) in zip(axes, metrics):
        def row_colour(row):
            val = row[col]
            if pd.isna(val):
                return NO_DATA_COLOUR
            return yes_colour if val == 'Y' else no_colour

        colours = merged.apply(row_colour, axis=1)
        merged.plot(ax=ax, color=colours, linewidth=0.3, edgecolor='white')

        ax.set_title(title, fontsize=11, fontweight='bold', pad=8)
        ax.axis('off')

        patches = [
            mpatches.Patch(color=yes_colour,     label='Yes'),
            mpatches.Patch(color=no_colour,      label='No'),
            mpatches.Patch(color=NO_DATA_COLOUR, label='No data'),
        ]
        ax.legend(handles=patches, loc='lower left', fontsize=8, framealpha=0.8)

        yes_count = (merged[col] == 'Y').sum()
        total     = merged[col].notna().sum()
        ax.annotate(
            f'{yes_count}/{total} ({yes_count/total*100:.0f}%)',
            xy=(0.5, 0.02), xycoords='axes fraction',
            ha='center', fontsize=9, color='#444444',
        )

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Small multiples written to {output_path}")


# ---------------------------------------------------------------------------
# Static score map (matplotlib)
# ---------------------------------------------------------------------------

def make_static_score_map(merged, output_path):
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))

    colours = merged.apply(get_colour, axis=1)
    merged.plot(ax=ax, color=colours, linewidth=0.3, edgecolor='white')

    ax.set_title(
        f'ccTLD Technical Maturity — {pd.Timestamp.now().strftime("%B %Y")}',
        fontsize=14, fontweight='bold', pad=12,
    )
    ax.axis('off')

    # Build legend - two entries per DNSSEC-positive band, one for others
    patches = []
    for s in sorted(SCORE_COLOURS.keys(), reverse=True):
        label = SCORE_LABELS[s].replace('\n', ' ')
        colours_for_score = SCORE_COLOURS[s]
        if s in DNSSEC_SCORES:
            patches.append(mpatches.Patch(
                color=colours_for_score['recommended'],
                label=f"{label} (recommended algorithm)"
            ))
            patches.append(mpatches.Patch(
                color=colours_for_score['other'],
                label=f"{label} (other algorithm)"
            ))
        else:
            patches.append(mpatches.Patch(
                color=colours_for_score['other'],
                label=label
            ))
    patches.append(mpatches.Patch(color=NO_DATA_COLOUR, label='No data / not assessed'))

    ax.legend(
        handles=patches,
        loc='lower left',
        fontsize=8,
        framealpha=0.9,
        title='Maturity Score\n(darker = recommended DNSSEC algorithm)',
        title_fontsize=8,
    )

    # Subtitle explaining the shading
    fig.text(
        0.5, 0.01,
        'Darker shades indicate use of a RECOMMENDED DNSSEC signing algorithm',
        ha='center', fontsize=8, color='#666666', style='italic'
    )

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Static score map written to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python visualise.py <results.csv>")
        print("  results.csv  Path to the ccTLD maturity CSV generated by the data gathering scripts")
        sys.exit(1)

    csv_path = sys.argv[1]

    if not os.path.exists(csv_path):
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df     = load_data(csv_path)
    world  = load_world()
    merged = merge_data(world, df)

    make_interactive_map(df,     os.path.join(OUTPUT_DIR, 'maturity_interactive.html'))
    make_static_score_map(merged, os.path.join(OUTPUT_DIR, 'maturity_score.png'))
    make_small_multiples(merged,  os.path.join(OUTPUT_DIR, 'maturity_multiples.png'))

    print("\nDone. Outputs:")
    print(f"  {OUTPUT_DIR}/maturity_interactive.html  — embeddable interactive map")
    print(f"  {OUTPUT_DIR}/maturity_score.png         — static consolidated maturity map")
    print(f"  {OUTPUT_DIR}/maturity_multiples.png     — detailed graphics by category")


if __name__ == '__main__':
    main()