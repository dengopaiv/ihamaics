# CMU Pronouncing Dictionary integration for SAM
# Provides better pronunciation for 134k+ English words

import os

# ARPABET to SAM phoneme mapping
# CMU uses ARPABET, SAM uses a similar but slightly different format
ARPABET_TO_SAM = {
    # Vowels (mostly identical)
    'AA': 'AA',   # odd
    'AE': 'AE',   # at
    'AH': 'AH',   # hut
    'AO': 'AO',   # ought
    'AW': 'AW',   # cow
    'AY': 'AY',   # hide
    'EH': 'EH',   # ed
    'ER': 'ER',   # hurt
    'EY': 'EY',   # ate
    'IH': 'IH',   # it
    'IY': 'IY',   # eat
    'OW': 'OW',   # oat
    'OY': 'OY',   # toy
    'UH': 'UH',   # hood
    'UW': 'UW',   # two

    # Consonants
    'B': 'B',
    'CH': 'CH',   # cheese
    'D': 'D',
    'DH': 'DH',   # thee
    'F': 'F',
    'G': 'G',
    'HH': '/H',   # he (SAM uses /H for H sound)
    'JH': 'J',    # gee
    'K': 'K',
    'L': 'L',
    'M': 'M',
    'N': 'N',
    'NG': 'NX',   # sing (SAM uses NX for ng)
    'P': 'P',
    'R': 'R',
    'S': 'S',
    'SH': 'SH',   # she
    'T': 'T',
    'TH': 'TH',   # theta
    'V': 'V',
    'W': 'W',
    'Y': 'Y',
    'Z': 'Z',
    'ZH': 'ZH',   # measure
}

# SAM stress markers: numbers 1-8 represent stress levels
# CMU uses 0=no stress, 1=primary, 2=secondary
# SAM: higher number = more stress
CMU_TO_SAM_STRESS = {
    '0': '',      # no stress marker
    '1': '4',     # primary stress
    '2': '2',     # secondary stress
}

# Global dictionary storage
_cmudict = None


def _get_dict_path():
    """Get path to cmudict.txt file."""
    return os.path.join(os.path.dirname(__file__), 'cmudict.txt')


def load_cmudict():
    """Load CMU dictionary from file."""
    global _cmudict
    if _cmudict is not None:
        return _cmudict

    _cmudict = {}
    dict_path = _get_dict_path()

    if not os.path.exists(dict_path):
        return _cmudict

    try:
        with open(dict_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(';;;'):
                    continue

                # Format: WORD  P1 P2 P3
                # or WORD(2)  P1 P2 P3 for alternate pronunciations
                parts = line.split()
                if len(parts) < 2:
                    continue

                word = parts[0].upper()
                # Remove alternate pronunciation markers like (2), (3)
                if '(' in word:
                    word = word.split('(')[0]

                phonemes = parts[1:]

                # Only store first pronunciation for each word
                if word not in _cmudict:
                    _cmudict[word] = phonemes

    except Exception:
        pass

    return _cmudict


def arpabet_to_sam(phonemes):
    """
    Convert ARPABET phoneme list to SAM phoneme string.

    Args:
        phonemes: List of ARPABET phonemes (e.g., ['HH', 'AH0', 'L', 'OW1'])

    Returns:
        SAM phoneme string (e.g., '/HAH4LOW4')
    """
    result = []

    for phoneme in phonemes:
        # Extract stress number from vowels (e.g., 'AH0' -> 'AH', '0')
        stress = ''
        base_phoneme = phoneme

        if phoneme and phoneme[-1] in '012':
            stress = phoneme[-1]
            base_phoneme = phoneme[:-1]

        # Map to SAM phoneme
        sam_phoneme = ARPABET_TO_SAM.get(base_phoneme, base_phoneme)

        # Add stress marker for vowels
        if stress:
            sam_stress = CMU_TO_SAM_STRESS.get(stress, '')
            result.append(sam_phoneme + sam_stress)
        else:
            result.append(sam_phoneme)

    return ''.join(result)


def lookup(word):
    """
    Look up a word in CMU dictionary and return SAM phonemes.

    Args:
        word: English word to look up

    Returns:
        SAM phoneme string, or None if not found
    """
    cmudict = load_cmudict()

    word_upper = word.upper().strip()
    if not word_upper:
        return None

    phonemes = cmudict.get(word_upper)
    if phonemes:
        return arpabet_to_sam(phonemes)

    return None


def is_loaded():
    """Check if dictionary is loaded."""
    return _cmudict is not None and len(_cmudict) > 0


def get_word_count():
    """Get number of words in dictionary."""
    cmudict = load_cmudict()
    return len(cmudict)
