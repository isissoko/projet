from django import template

from productions.formats import taille_lisible

register = template.Library()


@register.filter
def taille(octets):
    """{{ version.taille|taille }} → « 2,4 Mo »."""
    return taille_lisible(octets)
