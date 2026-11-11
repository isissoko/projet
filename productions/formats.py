"""Formats d'affichage en français."""


def taille_lisible(octets) -> str:
    """Taille en Ko / Mo avec virgule décimale : « 52,4 Mo », « 50 Mo », « 812 Ko »."""
    octets = int(octets or 0)
    if octets >= 1024 * 1024:
        valeur, unite = octets / (1024 * 1024), "Mo"
    elif octets >= 1024:
        valeur, unite = octets / 1024, "Ko"
    else:
        return f"{octets} octet{'s' if octets > 1 else ''}"
    texte = f"{valeur:.1f}".replace(".", ",").removesuffix(",0")
    return f"{texte} {unite}"
