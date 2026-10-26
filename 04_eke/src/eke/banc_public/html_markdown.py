"""`convert_to_markdown` de html-to-markdown 2.20.0, tel que le banc l'appelle, en bibliothèque standard.

Le banc passe chaque texte, sortie d'un outil comme texte attendu, par
`convert_to_markdown(texte, escape_asterisks=False, escape_underscores=False, escape_misc=False)`
avant de le comparer. La bibliothèque est un moteur Rust (caisse `html-to-markdown-rs` 2.20.0,
licence MIT, archive de crates.io de sha256 `b44ff13f...e5df934d21`) ; ce module en reprend :

- `validate_input` (`src/lib.rs`), à l'identique : un octet nul, plus de 30 % d'octets de
  contrôle dans les 8 192 premiers, ou un en-tête binaire font lever `EntreeRefusee`, comme la
  bibliothèque lève `ValueError` ;
- `fast_text_only` (`src/lib.rs`), à l'identique : le chemin de tout texte sans « < », qui décode
  les entités (caisse `html-escape` 0.2.13), réduit les blancs et termine par une fin de ligne ;
- pour un texte qui contient « < », le moteur analyse du HTML. Sa première étape
  (`preprocess_html` de `src/converter.rs`) remplace par « &lt; » chaque « < » qui n'ouvre pas de
  balise : ce module la reprend à l'identique. Un texte qui n'a plus alors de « < » est du texte
  seul pour le moteur, qui en traite les blancs à sa façon (`_texte_html`, relevée sur des sondes
  et vérifiée sur les textes réels, journal de l'étape 6). Pour une balise véritable ou ce qui en
  a l'air (« <b 's tra… » dans un texte d'OCR), le moteur fait du HTML (9 000 lignes) : ce module
  n'en a qu'une approximation, et `balise_veritable` signale ces textes.
"""

from __future__ import annotations

import html.entities
import re

LIMITE_ECHANTILLON = 8192
PART_CONTROLE = 0.3
PART_NULS_UTF16 = 0.2
ENTETES_BINAIRES = (
    (b"\x1f\x8b", "gzip-compressed data"),
    (b"\x28\xb5\x2f\xfd", "zstd-compressed data"),
    (b"PK\x03\x04", "zip archive"),
    (b"PK\x05\x06", "zip archive"),
    (b"PK\x07\x08", "zip archive"),
    (b"%PDF-", "PDF data"),
)
ESPACES_UNICODE = frozenset("               　")
"""`is_unicode_space` de `src/text.rs` : ramenés à une espace simple."""
ENTITES = {nom[:-1]: valeur[0] for nom, valeur in html.entities.html5.items() if nom.endswith(";")}
"""La table de `html-escape` 0.2.13 : les 2 125 noms du WHATWG terminés par « ; », réduits à leur
premier point de code (vérifié nom par nom le 2026-10-09 contre `src/decode/html_entity/tables.rs`)."""
CHIFFRES = re.compile(r"\+?[0-9]+")
CHIFFRES_HEXA = re.compile(r"\+?[0-9a-fA-F]+")


class EntreeRefusee(ValueError):
    """Ce que html-to-markdown refuse comme « binary data » ; le banc s'arrête alors sur une erreur."""


def valider(texte: str) -> None:
    """`validate_input` : refuse ce qui ressemble à des données binaires."""
    octets = texte.encode("utf-8")
    if not octets:
        return
    for entete, nom in ENTETES_BINAIRES:
        if octets.startswith(entete):
            raise EntreeRefusee(f"binary data detected ({nom})")
    echantillon = octets[:LIMITE_ECHANTILLON]
    controles = sum(1 for o in echantillon if o < 0x09 or 0x0E <= o < 0x20)
    nuls = [i for i, o in enumerate(echantillon) if o == 0]
    if nuls:
        if octets.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise EntreeRefusee("binary data detected (UTF-16 BOM)")
        pairs = sum(1 for i in nuls if i % 2 == 0)
        if len(nuls) / len(echantillon) >= PART_NULS_UTF16 and max(pairs, len(nuls) - pairs) / len(nuls) >= 0.9:
            raise EntreeRefusee("binary data detected (UTF-16 data without BOM)")
        raise EntreeRefusee("binary data detected")
    if controles / len(echantillon) > PART_CONTROLE:
        raise EntreeRefusee("binary data detected (excess control bytes)")


def _caractere(code: int) -> str | None:
    """`char::try_from(u32)` : None hors de l'Unicode ou pour une demi-paire UTF-16."""
    if code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
        return None
    return chr(code)


def decoder_entites(texte: str) -> str:
    """`html_escape::decode_html_entities` 0.2.13, son automate repris état par état.

    Après « & », tout jusqu'au « ; » suivant est le nom, même une espace ou un autre « & » :
    « R&D &amp; » ne décode rien. Les nombres suivent `u32::from_str` (un « + » permis).
    """
    if "&" not in texte:
        return texte
    morceaux: list[str] = []
    debut = 0
    etape = 0
    esperluette = 0
    for position, caractere in enumerate(texte):
        if etape == 0:
            if caractere == "&":
                etape, esperluette = 1, position
        elif etape == 1:
            etape = 3 if caractere == "#" else 0 if caractere == ";" else 2
        elif etape == 3:
            etape = 5 if caractere in "xX" else 0 if caractere == ";" else 4
        elif etape == 5:
            etape = 0 if caractere == ";" else 6
        elif caractere == ";":
            remplacement: str | None = None
            if etape == 2:
                remplacement = ENTITES.get(texte[esperluette + 1 : position])
            elif etape == 4:
                nombre = texte[esperluette + 2 : position]
                if CHIFFRES.fullmatch(nombre) and int(nombre) <= 0xFFFFFFFF:
                    remplacement = _caractere(int(nombre))
            else:
                nombre = texte[esperluette + 3 : position]
                if CHIFFRES_HEXA.fullmatch(nombre) and int(nombre, 16) <= 0xFFFFFFFF:
                    remplacement = _caractere(int(nombre, 16))
            etape = 0
            if remplacement is not None:
                morceaux.append(texte[debut:esperluette])
                morceaux.append(remplacement)
                debut = position + 1
    morceaux.append(texte[debut:])
    return "".join(morceaux)


def normaliser_blancs(texte: str) -> str:
    """`normalize_whitespace` : espaces, tabulations et espaces Unicode réduits à une espace ;
    les fins de ligne restent."""
    sortie: list[str] = []
    blanc_precedent = False
    for caractere in texte:
        if caractere in " \t" or caractere in ESPACES_UNICODE:
            if not blanc_precedent:
                sortie.append(" ")
                blanc_precedent = True
        else:
            sortie.append(caractere)
            blanc_precedent = False
    return "".join(sortie)


def _texte_seul(texte: str) -> str:
    """`fast_text_only`, options du banc : aucun échappement, pas de retour à la ligne forcé."""
    decode = decoder_entites(texte)
    coupe = decode.rstrip("\n")
    if not coupe:
        return ""
    sortie = normaliser_blancs(coupe).rstrip(" \t")
    return sortie + "\n"


def _texte_html(texte: str) -> str:
    """Du texte sans balise, passé par l'analyse HTML : entités décodées, blancs réduits comme au
    chemin rapide, mais pas d'espace avant une fin de ligne, les blancs de tête (fins de ligne
    comprises) réduits à une espace, ceux de queue retirés."""
    sortie = normaliser_blancs(decoder_entites(texte)).replace(" \n", "\n")
    if sortie[:1] in (" ", "\n"):
        sortie = " " + sortie.lstrip(" \n")
    sortie = sortie.rstrip(" \n")
    return sortie + "\n" if sortie else ""


BALISE = re.compile(r"<!--.*?(?:-->|\Z)|<[!?/]?[A-Za-z][^>]*(?:>|\Z)|<\?[^>]*(?:>|\Z)", re.DOTALL)
BLOCS = re.compile(
    r"</?(?:p|div|tr|li|ul|ol|h[1-6]|table|thead|tbody|blockquote|pre|hr|section|article)\b", re.IGNORECASE
)
SAUT = re.compile(r"<br\s*/?>", re.IGNORECASE)
MARQUE_SAUT = "\ue000"
"""Tient la place d'un `<br>` jusqu'au bout : le moteur en fait « deux espaces, fin de ligne »."""


def _ouvre_une_balise(texte: str, position: int) -> bool:
    """`is_valid_tag` de `preprocess_html` : ce qui suit « < » peut-il commencer une balise ?"""
    suivant = texte[position + 1 : position + 2]
    apres = texte[position + 2 : position + 3]
    if suivant == "!":
        return apres == "-" or (apres.isascii() and apres.isalpha())
    if suivant == "/":
        return apres.isascii() and apres.isalpha()
    return suivant == "?" or (suivant.isascii() and suivant.isalpha())


def echapper_chevrons(texte: str) -> str:
    """Chaque « < » qui n'ouvre pas de balise devient « &lt; », comme dans `preprocess_html`."""
    if "<" not in texte:
        return texte
    return "".join("&lt;" if c == "<" and not _ouvre_une_balise(texte, i) else c for i, c in enumerate(texte))


def balise_veritable(texte: str) -> bool:
    """Vrai si le texte a un « < » qui ouvre une balise : le moteur y fait du HTML, ce module
    n'en a qu'une approximation."""
    return "<" in echapper_chevrons(texte)


def _avec_balises(texte: str) -> str:
    """Approximation du HTML : balises retirées, `<br>` en saut de ligne Markdown, les blocs
    coupent la ligne ; puis le chemin du texte seul. Ce n'est pas le moteur ; ses écarts sont
    mesurés contre l'original."""
    morceaux: list[str] = []
    dernier = 0
    for balise in BALISE.finditer(texte):
        morceaux.append(texte[dernier : balise.start()])
        if SAUT.fullmatch(balise.group()):
            morceaux.append(MARQUE_SAUT)
        elif BLOCS.match(balise.group()):
            morceaux.append("\n")
        dernier = balise.end()
    morceaux.append(texte[dernier:])
    return _texte_html("".join(morceaux)).replace(MARQUE_SAUT, "  \n")


def convertir(texte: str) -> str:
    """`convert_to_markdown(texte, escape_asterisks=False, escape_underscores=False, escape_misc=False)`."""
    valider(texte)
    if "\r" in texte:
        texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    if "<" not in texte:
        return _texte_seul(texte)
    echappe = echapper_chevrons(texte)
    if "<" not in echappe:
        return _texte_html(echappe)
    return _avec_balises(echappe)
