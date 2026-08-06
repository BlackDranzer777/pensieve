"""Keyword rules for topic classification.

One place to edit. Adding a keyword or a language means changing this file and
nothing else — no code, no retraining, no labelled data.

Keywords are matched against **casefolded normalised text** on word-ish
boundaries, so "price" matches "The price is high" but not "priceless".

Two kinds of term:

    STRONG   unambiguous for the topic ("refund", "courier", "recyclable")
    WEAK     suggestive but shared across topics ("box", "site", "cost")

Strong matches score 2, weak score 1. That is what lets a review mentioning
both delivery and packaging resolve to a sensible primary topic instead of
whichever rule happened to run first.
"""

from __future__ import annotations

from typing import Final

from pipelines.common.domain import Topic

#: topic -> (strong terms, weak terms)
type TopicKeywords = dict[Topic, tuple[frozenset[str], frozenset[str]]]

STRONG_WEIGHT: Final[int] = 2
WEAK_WEIGHT: Final[int] = 1


TOPIC_KEYWORDS: Final[TopicKeywords] = {
    Topic.PRICE: (
        frozenset(
            {
                # en
                "price",
                "prices",
                "expensive",
                "overpriced",
                "cheaper",
                "pricing",
                "affordable",
                "value for money",
                # pl
                "cena",
                "ceny",
                "drogo",
                "tańszy",
                "drogie",
                # hi
                "कीमत",
                "महँगा",
                "सस्ता",
                "दाम",
                # fr
                "prix",
                "cher",
                "chère",
                "abordable",
                # de
                "preis",
                "teuer",
                "günstiger",
                "preis-leistungs-verhältnis",
                # es
                "precio",
                "caro",
                "barato",
                "asequible",
            }
        ),
        frozenset({"cost", "money", "worth", "pay", "koszt", "kosten", "coût", "costo"}),
    ),
    Topic.TASTE: (
        frozenset(
            {
                "taste",
                "tastes",
                "flavour",
                "flavor",
                "delicious",
                "bitter",
                "aftertaste",
                "smak",
                "smakował",
                "wyśmienity",
                "स्वाद",
                "स्वादिष्ट",
                "कड़वा",
                "goût",
                "savoureux",
                "amer",
                "geschmack",
                "schmeckt",
                "lecker",
                "sabor",
                "delicioso",
                "amargo",
                "rico",
            }
        ),
        frozenset({"sweet", "bland", "edible", "mild", "słodki", "süß", "dulce"}),
    ),
    Topic.PACKAGING: (
        frozenset(
            {
                "packaging",
                "packaged",
                "wrapped",
                "seal",
                "sealed",
                "opakowanie",
                "zapakowane",
                "पैकिंग",
                "पैकेजिंग",
                "डिब्बा",
                "emballage",
                "emballé",
                "verpackung",
                "verpackt",
                "embalaje",
                "empaquetado",
                "precinto",
            }
        ),
        frozenset({"box", "carton", "pudełko", "boîte", "schachtel", "caja", "डब्बा"}),
    ),
    Topic.DELIVERY: (
        frozenset(
            {
                "delivery",
                "delivered",
                "shipping",
                "shipped",
                "courier",
                "parcel",
                "dostawa",
                "kurier",
                "przesyłka",
                "wysyłka",
                "डिलीवरी",
                "कूरियर",
                "पहुँचा",
                "livraison",
                "livré",
                "colis",
                "coursier",
                "lieferung",
                "geliefert",
                "versand",
                "paket",
                "entrega",
                "envío",
                "mensajero",
                "paquete",
            }
        ),
        frozenset({"arrived", "late", "dotarł", "arrivé", "angekommen", "llegó"}),
    ),
    Topic.CUSTOMER_SUPPORT: (
        frozenset(
            {
                "customer service",
                "customer support",
                "support team",
                "helpline",
                "helpdesk",
                "obsługa klienta",
                "ग्राहक सेवा",
                "service client",
                "kundenservice",
                "kundendienst",
                "atención al cliente",
                "servicio al cliente",
            }
        ),
        frozenset({"support", "agent", "helpful", "replied", "email", "emails", "obsługa"}),
    ),
    Topic.WEBSITE_EXPERIENCE: (
        frozenset(
            {
                "website",
                "web site",
                "checkout",
                "app",
                "online experience",
                "strona",
                "strona internetowa",
                "वेबसाइट",
                "ऑनलाइन",
                "site web",
                "site internet",
                "webseite",
                "sitio web",
                "página web",
            }
        ),
        frozenset({"site", "browser", "login", "basket", "cart", "koszyk", "panier", "carrito"}),
    ),
    Topic.REFUNDS: (
        frozenset(
            {
                "refund",
                "refunded",
                "refunds",
                "return policy",
                "returned",
                "zwrot",
                "zwrot pieniędzy",
                "रिफंड",
                "वापसी",
                "remboursement",
                "remboursé",
                "rückerstattung",
                "erstattung",
                "reembolso",
                "devolución",
            }
        ),
        frozenset({"return", "money back", "exchange", "regulamin"}),
    ),
    Topic.AVAILABILITY: (
        frozenset(
            {
                "out of stock",
                "in stock",
                "restock",
                "sold out",
                "availability",
                "available",
                "niedostępny",
                "dostępny",
                "dostępność",
                "उपलब्ध",
                "स्टॉक",
                "rupture de stock",
                "disponible",
                "disponibilité",
                "verfügbar",
                "verfügbarkeit",
                "ausverkauft",
                "agotado",
                "disponibilidad",
            }
        ),
        frozenset({"stock", "supply", "zapas", "vorrat"}),
    ),
    Topic.PRODUCT_QUALITY: (
        frozenset(
            {
                "quality",
                "build quality",
                "durable",
                "well made",
                "badly made",
                "fell apart",
                "jakość",
                "trwały",
                "wykonania",
                "गुणवत्ता",
                "मजबूत",
                "टूट",
                "qualité",
                "solide",
                "fabrication",
                "qualität",
                "verarbeitung",
                "langlebig",
                "calidad",
                "resistente",
                "fabricación",
            }
        ),
        frozenset({"broke", "broken", "sturdy", "flimsy", "zepsuł", "cassé", "kaputt", "rompió"}),
    ),
    Topic.SUSTAINABILITY: (
        frozenset(
            {
                "recyclable",
                "recycling",
                "sustainable",
                "sustainability",
                "eco friendly",
                "eco-friendly",
                "plastic free",
                "ethical",
                "recyklingu",
                "ekologiczne",
                "रीसायकल",
                "पर्यावरण",
                "écologique",
                "durable",
                "recycelbar",
                "nachhaltig",
                "umweltfreundlich",
                "reciclable",
                "sostenible",
                "ecológico",
            }
        ),
        frozenset({"plastic", "waste", "packaging waste", "plastik", "plastique", "plástico"}),
    ),
}


def all_keywords() -> set[str]:
    """Every configured keyword, for coverage checks and documentation."""
    terms: set[str] = set()
    for strong, weak in TOPIC_KEYWORDS.values():
        terms |= set(strong) | set(weak)
    return terms
