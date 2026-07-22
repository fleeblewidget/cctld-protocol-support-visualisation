import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from .config import GROUP_COLOURS, DNSSEC_ALGORITHM_COLOURS, NO_DATA_COLOUR

# ---------------------------------------------------------------------------
# Bar graphs with counts (matplotlib)
# ---------------------------------------------------------------------------

def make_protocol_charts(df, output_path):
    total = len(df)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 5))
    fig.suptitle(
        f'ccTLD Protocol Adoption & DNSSEC Algorithms — {pd.Timestamp.now().strftime("%B %Y")}',
        fontsize=13, fontweight='bold', y=1.02
    )

    # --- Left: Protocol adoption ---
    protocols = [
        ('ds',    'DNSSEC', GROUP_COLOURS[5]),
        ('whois', 'WHOIS',  GROUP_COLOURS[3]),
        ('rdap',  'RDAP',   GROUP_COLOURS[4]),
        ('ipv6',  'IPv6',   '#6610f2'),
    ]

    counts  = [(label, (df[col] == 'Y').sum(), colour)
               for col, label, colour in protocols]
    labels  = [c[0] for c in counts]
    values  = [c[1] for c in counts]
    colours = [c[2] for c in counts]

    bars = ax1.barh(labels, values, color=colours, height=0.5, zorder=2)

    ax1.axvline(x=total, color='#333333', linewidth=1.5,
                linestyle='--', zorder=3)

    for bar, val in zip(bars, values):
        pct = val / total * 100
        ax1.text(
            bar.get_width() + 2, bar.get_y() + bar.get_height() / 2,
            f'{val}\n({pct:.0f}%)',
            va='center', ha='left', fontsize=10
        )

    ax1.set_xlim(0, total * 1.18)
    ax1.set_xlabel('Number of ccTLDs', fontsize=10)
    ax1.set_title('Protocol Adoption', fontsize=11, fontweight='bold', pad=8)
    ax1.legend(fontsize=9)
    ax1.grid(axis='x', alpha=0.3, zorder=1)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # --- Right: DNSSEC algorithm breakdown ---
    signed = df[df['ds'] == 'Y'].copy()

    RECOMMENDATION_ORDER = ['RECOMMENDED', 'MAY', 'NOT RECOMMENDED', 'MUST NOT']

    alg_counts = (
        signed.groupby(['ds_algorithm_name', 'ds_algorithm_status'])
        .size()
        .reset_index(name='count')
    )

    # Sort by recommendation level, then by count descending within each level
    alg_counts['rec_order'] = alg_counts['ds_algorithm_status'].map(
        {status: i for i, status in enumerate(RECOMMENDATION_ORDER)}
    )
    alg_counts = (alg_counts
        .sort_values(['rec_order', 'count'], ascending=[False, True])
        .drop(columns='rec_order'))

    alg_labels  = [
        f"{row['ds_algorithm_name']} ({row['ds_algorithm_status']})"
        for _, row in alg_counts.iterrows()
    ]
    alg_values  = alg_counts['count'].tolist()
    alg_colours = [
        DNSSEC_ALGORITHM_COLOURS.get(row['ds_algorithm_status'], NO_DATA_COLOUR)
        for _, row in alg_counts.iterrows()
    ]

    bars2 = ax2.barh(alg_labels, alg_values, color=alg_colours, height=0.5, zorder=2)

    for bar, val in zip(bars2, alg_values):
        ax2.text(
            bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
            str(val),
            va='center', ha='left', fontsize=10
        )

    ax2.set_xlim(0, max(alg_values) * 1.18)
    ax2.set_xlabel('Number of ccTLDs', fontsize=10)
    ax2.set_title('DNSSEC Signing Algorithm', fontsize=11, fontweight='bold', pad=8)

    patches = [
        mpatches.Patch(color=v, label=k)
        for k, v in DNSSEC_ALGORITHM_COLOURS.items()
        if k != 'n/a'
    ]
    ax2.legend(handles=patches, fontsize=9, title='Recommendation', title_fontsize=9)
    ax2.grid(axis='x', alpha=0.3, zorder=1)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Protocol charts written to {output_path}")