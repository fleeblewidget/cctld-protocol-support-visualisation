# Data manipulation methods

import geopandas as gpd
import pandas as pd
import pycountry

from .config import GROUP_LABELS, REQUIRED_COLUMNS

# ccTLD label -> ISO 3166-1 alpha-2 exceptions
# Most ccTLDs map directly (label.upper() == ISO code) but these don't
ISO_EXCEPTIONS = {
    'uk': 'GB'  # ISO code for UK is GB
}

# TLDs to exclude from the map entirely (unassigned, regional, unused etc.)
# Note that .ac is in use at time of writing, but the visualisations use
# the larger .sh
EXCLUDE = {'eu', 'su', 'gb', 'ac'}

def validate_csv(df):
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
    
    # Check expected values
    invalid_ds = df[~df['ds'].isin(['Y', 'N'])]
    if not invalid_ds.empty:
        raise ValueError(f"Unexpected values in 'ds' column: {invalid_ds['ds'].unique()}")
    
    invalid_rdap = df[~df['rdap'].isin(['Y', 'N'])]
    if not invalid_rdap.empty:
        raise ValueError(f"Unexpected values in 'rdap' column: {invalid_rdap['rdap'].unique()}")

    print(f"CSV validation passed: {len(df)} rows, all expected columns present")

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

# Grouping rules - returns 0-5 for mapping to colours
# 5: DNSSEC + RDAP
# 4: RDAP only
# 3: DNSSEC + WHOIS
# 2: DNSSEC only
# 1: WHOIS only
# 0: no supported protocols

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