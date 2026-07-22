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

DNSSEC_ALGORITHM_COLOURS = {
    'RECOMMENDED':     '#2a9d8f',
    'MAY':             '#8ecae6',
    'NOT RECOMMENDED': '#e9c46a',
    'MUST NOT':        '#e63946',
    'n/a':             '#aaaaaa',  # no DNSSEC
}

NO_DATA_COLOUR = '#cccccc'