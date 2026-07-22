import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px

from .config import GROUP_COLOURS, GROUP_LABELS, NO_DATA_COLOUR

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
