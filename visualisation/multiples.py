import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from .config import DNSSEC_ALGORITHM_COLOURS, NO_DATA_COLOUR

# ---------------------------------------------------------------------------
# Static small multiples (matplotlib) - one map per metric
# ---------------------------------------------------------------------------

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
