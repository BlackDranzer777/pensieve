"""Review text templates for the synthetic generator.

Each template is real text in its language, written to contain the vocabulary a
keyword-based topic classifier would look for and the sentiment cues a
transformer would pick up. Generating lorem ipsum would produce a dataset that
looks plausible in a table and is useless for testing enrichment.

Structure: `TEMPLATES[language][topic][sentiment] -> list[str]`

`{product}` is substituted with the product name at generation time.

Extending a language means adding its ISO code here and to
`pipelines.common.domain.Language`. Topics without templates for a given
language simply produce fewer rows for that combination — a missing entry is
not an error.
"""

from __future__ import annotations

from typing import Final

from pipelines.common.domain import Language, Sentiment, Topic

# A template bank: topic -> sentiment -> phrasings.
TemplateBank = dict[Topic, dict[Sentiment, list[str]]]


_ENGLISH: TemplateBank = {
    Topic.PRICE: {
        Sentiment.POSITIVE: [
            "Great value for money, the {product} costs far less than competitors.",
            "Excellent price, honestly cheaper than I expected for this quality.",
        ],
        Sentiment.NEGATIVE: [
            "Far too expensive. The price of the {product} has doubled and it is not worth it.",
            "Overpriced for what you get. I will not pay this much again.",
        ],
        Sentiment.NEUTRAL: [
            "The price of the {product} is about average for this category.",
            "Cost is reasonable, neither cheap nor expensive.",
        ],
    },
    Topic.TASTE: {
        Sentiment.POSITIVE: [
            "The flavour of this {product} is delicious, rich and not too sweet.",
            "Tastes fantastic. Best flavour I have had in this range.",
        ],
        Sentiment.NEGATIVE: [
            "Awful taste, the {product} was bitter and had a strange aftertaste.",
            "The flavour is bland and artificial. Could not finish it.",
        ],
        Sentiment.NEUTRAL: [
            "The taste is fine, nothing remarkable but perfectly edible.",
            "Flavour is as described, quite mild.",
        ],
    },
    Topic.PACKAGING: {
        Sentiment.POSITIVE: [
            "The packaging was sturdy and the {product} arrived in perfect condition.",
            "Lovely box design and everything was well protected inside.",
        ],
        Sentiment.NEGATIVE: [
            "The packaging was crushed and the seal on the {product} was broken.",
            "Terrible packaging, the box was leaking when it arrived.",
        ],
        Sentiment.NEUTRAL: [
            "Standard packaging, nothing special but it did the job.",
            "The box was plain but adequate.",
        ],
    },
    Topic.DELIVERY: {
        Sentiment.POSITIVE: [
            "Delivery was incredibly fast, the {product} arrived a day early.",
            "Shipping was quick and the courier was very helpful.",
        ],
        Sentiment.NEGATIVE: [
            "Delivery was three weeks late and nobody could tell me where the parcel was.",
            "Shipping is far too slow. The courier left my order in the rain.",
        ],
        Sentiment.NEUTRAL: [
            "Delivery took the number of days stated at checkout.",
            "Shipping was on schedule, no issues to report.",
        ],
    },
    Topic.CUSTOMER_SUPPORT: {
        Sentiment.POSITIVE: [
            "Customer service resolved my issue with the {product} within an hour.",
            "The support team were polite, patient and genuinely helpful.",
        ],
        Sentiment.NEGATIVE: [
            "Customer support never replied to three emails about my {product}.",
            "The helpline kept me waiting forty minutes and then hung up.",
        ],
        Sentiment.NEUTRAL: [
            "Contacted customer service and they answered the question adequately.",
            "Support replied within the stated timeframe.",
        ],
    },
    Topic.WEBSITE_EXPERIENCE: {
        Sentiment.POSITIVE: [
            "The website is clean and checkout took less than a minute.",
            "Easy to navigate the site and the search actually found what I wanted.",
        ],
        Sentiment.NEGATIVE: [
            "The website crashed twice during checkout and lost my basket.",
            "Awful online experience, the app kept logging me out.",
        ],
        Sentiment.NEUTRAL: [
            "The website works well enough, the layout is conventional.",
            "Ordering online was straightforward.",
        ],
    },
    Topic.REFUNDS: {
        Sentiment.POSITIVE: [
            "The refund for my {product} was processed in two days, no arguments.",
            "Returning the item was simple and the money came back quickly.",
        ],
        Sentiment.NEGATIVE: [
            "Still waiting for a refund six weeks after returning the {product}.",
            "They refused my return even though the item was faulty.",
        ],
        Sentiment.NEUTRAL: [
            "The refund was processed within the stated policy window.",
            "Return process was standard for this kind of retailer.",
        ],
    },
    Topic.AVAILABILITY: {
        Sentiment.POSITIVE: [
            "Always in stock, I have never had trouble finding the {product}.",
            "Good availability across sizes, everything I wanted was there.",
        ],
        Sentiment.NEGATIVE: [
            "The {product} has been out of stock for months with no restock date.",
            "Never available in my size. Stock levels are hopeless.",
        ],
        Sentiment.NEUTRAL: [
            "Availability varies but I usually find what I need eventually.",
            "Stock seems to depend on the time of month.",
        ],
    },
    Topic.PRODUCT_QUALITY: {
        Sentiment.POSITIVE: [
            "Outstanding build quality, the {product} feels durable and well made.",
            "Excellent quality, it has lasted far longer than I expected.",
        ],
        Sentiment.NEGATIVE: [
            "Poor quality, the {product} broke after two weeks of normal use.",
            "Feels cheap and badly made. It fell apart almost immediately.",
        ],
        Sentiment.NEUTRAL: [
            "Quality is acceptable for the price bracket.",
            "The build is reasonable, comparable to similar products.",
        ],
    },
    Topic.SUSTAINABILITY: {
        Sentiment.POSITIVE: [
            "Love that the packaging is recyclable and the sourcing is ethical.",
            "Genuinely sustainable materials, plastic free and clearly labelled.",
        ],
        Sentiment.NEGATIVE: [
            "So much plastic waste. The {product} came wrapped three times over.",
            "Claims to be eco friendly but the packaging is not recyclable at all.",
        ],
        Sentiment.NEUTRAL: [
            "The packaging is partly recyclable according to the label.",
            "Sustainability information is provided on the box.",
        ],
    },
}


_POLISH: TemplateBank = {
    Topic.PRICE: {
        Sentiment.POSITIVE: ["Świetna cena, {product} jest tańszy niż u konkurencji."],
        Sentiment.NEGATIVE: ["Zdecydowanie za drogo. Cena jest absurdalnie wysoka."],
        Sentiment.NEUTRAL: ["Cena jest przeciętna, typowa dla tej kategorii."],
    },
    Topic.TASTE: {
        Sentiment.POSITIVE: ["Smak jest wyśmienity, {product} bardzo mi smakował."],
        Sentiment.NEGATIVE: ["Okropny smak, gorzki i sztuczny. Nie dokończyłem."],
        Sentiment.NEUTRAL: ["Smak jest w porządku, nic szczególnego."],
    },
    Topic.PACKAGING: {
        Sentiment.POSITIVE: ["Opakowanie solidne, {product} dotarł nieuszkodzony."],
        Sentiment.NEGATIVE: ["Opakowanie było zgniecione, a plomba zerwana."],
        Sentiment.NEUTRAL: ["Standardowe opakowanie, spełnia swoją rolę."],
    },
    Topic.DELIVERY: {
        Sentiment.POSITIVE: ["Dostawa błyskawiczna, przesyłka przyszła dzień wcześniej."],
        Sentiment.NEGATIVE: ["Dostawa spóźniona o trzy tygodnie. Kurier nic nie wiedział."],
        Sentiment.NEUTRAL: ["Wysyłka zgodna z podanym terminem."],
    },
    Topic.CUSTOMER_SUPPORT: {
        Sentiment.POSITIVE: ["Obsługa klienta rozwiązała mój problem w godzinę."],
        Sentiment.NEGATIVE: ["Obsługa klienta nie odpowiedziała na żaden z moich e-maili."],
        Sentiment.NEUTRAL: ["Kontakt z obsługą przebiegł zgodnie z oczekiwaniami."],
    },
    Topic.WEBSITE_EXPERIENCE: {
        Sentiment.POSITIVE: ["Strona działa szybko, zamówienie złożyłem w minutę."],
        Sentiment.NEGATIVE: ["Strona zawiesiła się podczas płatności i koszyk zniknął."],
        Sentiment.NEUTRAL: ["Strona internetowa działa poprawnie."],
    },
    Topic.REFUNDS: {
        Sentiment.POSITIVE: ["Zwrot pieniędzy otrzymałem w dwa dni, bez problemów."],
        Sentiment.NEGATIVE: ["Czekam na zwrot pieniędzy już sześć tygodni."],
        Sentiment.NEUTRAL: ["Zwrot przebiegł zgodnie z regulaminem."],
    },
    Topic.AVAILABILITY: {
        Sentiment.POSITIVE: ["Produkt zawsze dostępny, nigdy nie miałem problemu."],
        Sentiment.NEGATIVE: ["{product} niedostępny od miesięcy, brak informacji o dostawie."],
        Sentiment.NEUTRAL: ["Dostępność bywa różna, ale zwykle znajdę co potrzebuję."],
    },
    Topic.PRODUCT_QUALITY: {
        Sentiment.POSITIVE: ["Doskonała jakość wykonania, {product} jest bardzo trwały."],
        Sentiment.NEGATIVE: ["Kiepska jakość, {product} zepsuł się po dwóch tygodniach."],
        Sentiment.NEUTRAL: ["Jakość akceptowalna jak na tę półkę cenową."],
    },
    Topic.SUSTAINABILITY: {
        Sentiment.POSITIVE: ["Opakowanie nadaje się do recyklingu, materiały ekologiczne."],
        Sentiment.NEGATIVE: ["Mnóstwo plastiku. Rzekomo ekologiczne, a wcale nie jest."],
        Sentiment.NEUTRAL: ["Informacja o recyklingu znajduje się na opakowaniu."],
    },
}


_HINDI: TemplateBank = {
    Topic.PRICE: {
        Sentiment.POSITIVE: ["कीमत बहुत अच्छी है, {product} दूसरों से सस्ता है।"],
        Sentiment.NEGATIVE: ["बहुत महँगा है। इस कीमत पर यह बिल्कुल सही नहीं है।"],
        Sentiment.NEUTRAL: ["कीमत औसत है, इस श्रेणी के लिए सामान्य।"],
    },
    Topic.TASTE: {
        Sentiment.POSITIVE: ["स्वाद बहुत बढ़िया है, {product} बहुत स्वादिष्ट लगा।"],
        Sentiment.NEGATIVE: ["स्वाद खराब था, कड़वा और अजीब सा लगा।"],
        Sentiment.NEUTRAL: ["स्वाद ठीक है, कुछ खास नहीं।"],
    },
    Topic.PACKAGING: {
        Sentiment.POSITIVE: ["पैकिंग मजबूत थी, {product} बिल्कुल सही हालत में पहुँचा।"],
        Sentiment.NEGATIVE: ["पैकिंग टूटी हुई थी और सील खुली हुई थी।"],
        Sentiment.NEUTRAL: ["पैकिंग सामान्य थी, काम चल गया।"],
    },
    Topic.DELIVERY: {
        Sentiment.POSITIVE: ["डिलीवरी बहुत तेज़ थी, सामान एक दिन पहले आ गया।"],
        Sentiment.NEGATIVE: ["डिलीवरी तीन हफ्ते लेट थी और कोई जानकारी नहीं मिली।"],
        Sentiment.NEUTRAL: ["डिलीवरी बताए गए समय पर हुई।"],
    },
    Topic.CUSTOMER_SUPPORT: {
        Sentiment.POSITIVE: ["ग्राहक सेवा ने एक घंटे में मेरी समस्या हल कर दी।"],
        Sentiment.NEGATIVE: ["ग्राहक सेवा ने मेरे किसी भी ईमेल का जवाब नहीं दिया।"],
        Sentiment.NEUTRAL: ["ग्राहक सेवा से बात हुई, जवाब ठीक था।"],
    },
    Topic.WEBSITE_EXPERIENCE: {
        Sentiment.POSITIVE: ["वेबसाइट बहुत आसान है, ऑर्डर एक मिनट में हो गया।"],
        Sentiment.NEGATIVE: ["वेबसाइट भुगतान के समय बंद हो गई और कार्ट खाली हो गया।"],
        Sentiment.NEUTRAL: ["वेबसाइट ठीक से काम करती है।"],
    },
    Topic.REFUNDS: {
        Sentiment.POSITIVE: ["रिफंड दो दिन में मिल गया, कोई परेशानी नहीं।"],
        Sentiment.NEGATIVE: ["वापसी के छह हफ्ते बाद भी रिफंड नहीं मिला।"],
        Sentiment.NEUTRAL: ["रिफंड नीति के अनुसार हुआ।"],
    },
    Topic.AVAILABILITY: {
        Sentiment.POSITIVE: ["{product} हमेशा उपलब्ध रहता है, कभी दिक्कत नहीं हुई।"],
        Sentiment.NEGATIVE: ["{product} महीनों से स्टॉक में नहीं है।"],
        Sentiment.NEUTRAL: ["उपलब्धता बदलती रहती है।"],
    },
    Topic.PRODUCT_QUALITY: {
        Sentiment.POSITIVE: ["गुणवत्ता शानदार है, {product} बहुत मजबूत है।"],
        Sentiment.NEGATIVE: ["गुणवत्ता खराब है, {product} दो हफ्ते में टूट गया।"],
        Sentiment.NEUTRAL: ["गुणवत्ता कीमत के हिसाब से ठीक है।"],
    },
    Topic.SUSTAINABILITY: {
        Sentiment.POSITIVE: ["पैकिंग रीसायकल हो सकती है, सामग्री पर्यावरण के अनुकूल है।"],
        Sentiment.NEGATIVE: ["बहुत ज्यादा प्लास्टिक है, पर्यावरण के लिए ठीक नहीं।"],
        Sentiment.NEUTRAL: ["रीसायकलिंग की जानकारी डिब्बे पर दी गई है।"],
    },
}


_FRENCH: TemplateBank = {
    Topic.PRICE: {
        Sentiment.POSITIVE: [
            "Très bon rapport qualité prix, {product} coûte moins cher qu'ailleurs."
        ],
        Sentiment.NEGATIVE: ["Beaucoup trop cher. Le prix a doublé et ça ne les vaut pas."],
        Sentiment.NEUTRAL: ["Le prix est dans la moyenne de la catégorie."],
    },
    Topic.TASTE: {
        Sentiment.POSITIVE: ["Le goût est délicieux, {product} est vraiment savoureux."],
        Sentiment.NEGATIVE: ["Goût affreux, amer avec un arrière goût étrange."],
        Sentiment.NEUTRAL: ["Le goût est correct, sans plus."],
    },
    Topic.PACKAGING: {
        Sentiment.POSITIVE: ["Emballage solide, {product} est arrivé en parfait état."],
        Sentiment.NEGATIVE: ["L'emballage était écrasé et le sceau était brisé."],
        Sentiment.NEUTRAL: ["Emballage standard, rien de particulier."],
    },
    Topic.DELIVERY: {
        Sentiment.POSITIVE: ["Livraison très rapide, le colis est arrivé un jour en avance."],
        Sentiment.NEGATIVE: ["Livraison en retard de trois semaines, aucune information."],
        Sentiment.NEUTRAL: ["La livraison a respecté le délai annoncé."],
    },
    Topic.CUSTOMER_SUPPORT: {
        Sentiment.POSITIVE: ["Le service client a résolu mon problème en une heure."],
        Sentiment.NEGATIVE: ["Le service client n'a répondu à aucun de mes courriels."],
        Sentiment.NEUTRAL: ["Le service client a répondu dans les délais annoncés."],
    },
    Topic.WEBSITE_EXPERIENCE: {
        Sentiment.POSITIVE: ["Le site est clair et la commande a pris moins d'une minute."],
        Sentiment.NEGATIVE: ["Le site a planté pendant le paiement et mon panier a disparu."],
        Sentiment.NEUTRAL: ["Le site fonctionne correctement."],
    },
    Topic.REFUNDS: {
        Sentiment.POSITIVE: ["Remboursement effectué en deux jours, sans discussion."],
        Sentiment.NEGATIVE: ["J'attends toujours mon remboursement depuis six semaines."],
        Sentiment.NEUTRAL: ["Le remboursement a suivi la politique annoncée."],
    },
    Topic.AVAILABILITY: {
        Sentiment.POSITIVE: ["Toujours en stock, je n'ai jamais eu de problème."],
        Sentiment.NEGATIVE: ["{product} est en rupture de stock depuis des mois."],
        Sentiment.NEUTRAL: ["La disponibilité varie selon les périodes."],
    },
    Topic.PRODUCT_QUALITY: {
        Sentiment.POSITIVE: ["Qualité de fabrication remarquable, {product} est très solide."],
        Sentiment.NEGATIVE: ["Mauvaise qualité, {product} a cassé au bout de deux semaines."],
        Sentiment.NEUTRAL: ["La qualité est acceptable pour ce prix."],
    },
    Topic.SUSTAINABILITY: {
        Sentiment.POSITIVE: ["Emballage recyclable et matériaux vraiment écologiques."],
        Sentiment.NEGATIVE: ["Beaucoup trop de plastique, l'emballage n'est pas recyclable."],
        Sentiment.NEUTRAL: ["Les informations de recyclage figurent sur la boîte."],
    },
}


_GERMAN: TemplateBank = {
    Topic.PRICE: {
        Sentiment.POSITIVE: [
            "Sehr gutes Preis-Leistungs-Verhältnis, {product} ist günstiger als anderswo."
        ],
        Sentiment.NEGATIVE: ["Viel zu teuer. Der Preis hat sich verdoppelt und lohnt sich nicht."],
        Sentiment.NEUTRAL: ["Der Preis ist durchschnittlich für diese Kategorie."],
    },
    Topic.TASTE: {
        Sentiment.POSITIVE: ["Der Geschmack ist hervorragend, {product} schmeckt wirklich gut."],
        Sentiment.NEGATIVE: ["Schrecklicher Geschmack, bitter und künstlich."],
        Sentiment.NEUTRAL: ["Der Geschmack ist in Ordnung, nichts Besonderes."],
    },
    Topic.PACKAGING: {
        Sentiment.POSITIVE: ["Stabile Verpackung, {product} kam unbeschädigt an."],
        Sentiment.NEGATIVE: ["Die Verpackung war zerdrückt und das Siegel gebrochen."],
        Sentiment.NEUTRAL: ["Standardverpackung, erfüllt ihren Zweck."],
    },
    Topic.DELIVERY: {
        Sentiment.POSITIVE: ["Lieferung war sehr schnell, das Paket kam einen Tag früher."],
        Sentiment.NEGATIVE: ["Lieferung war drei Wochen zu spät und niemand konnte helfen."],
        Sentiment.NEUTRAL: ["Der Versand erfolgte innerhalb der angegebenen Zeit."],
    },
    Topic.CUSTOMER_SUPPORT: {
        Sentiment.POSITIVE: ["Der Kundenservice hat mein Problem innerhalb einer Stunde gelöst."],
        Sentiment.NEGATIVE: ["Der Kundenservice hat auf keine meiner E-Mails geantwortet."],
        Sentiment.NEUTRAL: ["Der Kundenservice hat fristgerecht geantwortet."],
    },
    Topic.WEBSITE_EXPERIENCE: {
        Sentiment.POSITIVE: ["Die Webseite ist übersichtlich und die Bestellung ging schnell."],
        Sentiment.NEGATIVE: [
            "Die Webseite ist beim Bezahlen abgestürzt und der Warenkorb war leer."
        ],
        Sentiment.NEUTRAL: ["Die Webseite funktioniert einwandfrei."],
    },
    Topic.REFUNDS: {
        Sentiment.POSITIVE: ["Die Rückerstattung erfolgte innerhalb von zwei Tagen."],
        Sentiment.NEGATIVE: ["Ich warte seit sechs Wochen auf meine Rückerstattung."],
        Sentiment.NEUTRAL: ["Die Rückgabe verlief nach den angegebenen Bedingungen."],
    },
    Topic.AVAILABILITY: {
        Sentiment.POSITIVE: ["Immer auf Lager, ich hatte nie Probleme."],
        Sentiment.NEGATIVE: ["{product} ist seit Monaten nicht verfügbar."],
        Sentiment.NEUTRAL: ["Die Verfügbarkeit schwankt je nach Zeitpunkt."],
    },
    Topic.PRODUCT_QUALITY: {
        Sentiment.POSITIVE: ["Hervorragende Verarbeitung, {product} ist sehr langlebig."],
        Sentiment.NEGATIVE: ["Schlechte Qualität, {product} ging nach zwei Wochen kaputt."],
        Sentiment.NEUTRAL: ["Die Qualität ist für diesen Preis akzeptabel."],
    },
    Topic.SUSTAINABILITY: {
        Sentiment.POSITIVE: ["Recycelbare Verpackung und wirklich nachhaltige Materialien."],
        Sentiment.NEGATIVE: ["Viel zu viel Plastik, die Verpackung ist nicht recycelbar."],
        Sentiment.NEUTRAL: ["Recyclinghinweise stehen auf der Verpackung."],
    },
}


_SPANISH: TemplateBank = {
    Topic.PRICE: {
        Sentiment.POSITIVE: [
            "Muy buena relación calidad precio, {product} cuesta menos que otros."
        ],
        Sentiment.NEGATIVE: ["Demasiado caro. El precio se ha duplicado y no lo vale."],
        Sentiment.NEUTRAL: ["El precio es normal para esta categoría."],
    },
    Topic.TASTE: {
        Sentiment.POSITIVE: ["El sabor es delicioso, {product} está muy rico."],
        Sentiment.NEGATIVE: ["Sabor horrible, amargo y con un regusto extraño."],
        Sentiment.NEUTRAL: ["El sabor está bien, nada especial."],
    },
    Topic.PACKAGING: {
        Sentiment.POSITIVE: ["El embalaje era resistente y {product} llegó en perfecto estado."],
        Sentiment.NEGATIVE: ["El embalaje estaba aplastado y el precinto roto."],
        Sentiment.NEUTRAL: ["Embalaje estándar, cumple su función."],
    },
    Topic.DELIVERY: {
        Sentiment.POSITIVE: ["El envío fue rapidísimo, llegó un día antes de lo previsto."],
        Sentiment.NEGATIVE: ["La entrega se retrasó tres semanas y nadie sabía nada."],
        Sentiment.NEUTRAL: ["El envío llegó en el plazo indicado."],
    },
    Topic.CUSTOMER_SUPPORT: {
        Sentiment.POSITIVE: ["Atención al cliente resolvió mi problema en una hora."],
        Sentiment.NEGATIVE: ["Atención al cliente no respondió a ninguno de mis correos."],
        Sentiment.NEUTRAL: ["El servicio de atención respondió dentro del plazo."],
    },
    Topic.WEBSITE_EXPERIENCE: {
        Sentiment.POSITIVE: ["La web es clara y el pago tardó menos de un minuto."],
        Sentiment.NEGATIVE: ["La web se cayó durante el pago y perdí el carrito."],
        Sentiment.NEUTRAL: ["La página web funciona correctamente."],
    },
    Topic.REFUNDS: {
        Sentiment.POSITIVE: ["El reembolso se procesó en dos días, sin problemas."],
        Sentiment.NEGATIVE: ["Llevo seis semanas esperando el reembolso de mi devolución."],
        Sentiment.NEUTRAL: ["La devolución siguió la política indicada."],
    },
    Topic.AVAILABILITY: {
        Sentiment.POSITIVE: ["Siempre hay stock, nunca he tenido problemas."],
        Sentiment.NEGATIVE: ["{product} lleva meses agotado sin fecha de reposición."],
        Sentiment.NEUTRAL: ["La disponibilidad varía según la época."],
    },
    Topic.PRODUCT_QUALITY: {
        Sentiment.POSITIVE: ["Calidad excelente, {product} es muy resistente."],
        Sentiment.NEGATIVE: ["Mala calidad, {product} se rompió a las dos semanas."],
        Sentiment.NEUTRAL: ["La calidad es aceptable para este precio."],
    },
    Topic.SUSTAINABILITY: {
        Sentiment.POSITIVE: ["Embalaje reciclable y materiales realmente sostenibles."],
        Sentiment.NEGATIVE: ["Demasiado plástico, el embalaje no es reciclable."],
        Sentiment.NEUTRAL: ["La información de reciclaje aparece en la caja."],
    },
}


TEMPLATES: Final[dict[Language, TemplateBank]] = {
    Language.ENGLISH: _ENGLISH,
    Language.POLISH: _POLISH,
    Language.HINDI: _HINDI,
    Language.FRENCH: _FRENCH,
    Language.GERMAN: _GERMAN,
    Language.SPANISH: _SPANISH,
}

# --- Variation fragments ----------------------------------------------------
# Optional openers and closers combined with the templates above.
#
# Without these, a bank of ~1 template per (language, topic, sentiment) makes
# genuinely different reviews produce byte-identical text, and the content
# deduplicator correctly but uselessly reports ~46% duplicates. Real customers
# do not write identical sentences, so the generator should not either.
#
# With roughly 6 openers x 8 closers the combinatorial space per template is
# ~48x larger, which puts the observed duplicate rate close to the rate we
# actually inject on purpose.

OPENERS: Final[dict[Language, tuple[str, ...]]] = {
    Language.ENGLISH: ("", "", "Honestly, ", "To be fair, ", "First of all, ", "Overall, "),
    Language.POLISH: ("", "", "Szczerze mówiąc, ", "Ogólnie rzecz biorąc, ", "Po pierwsze, "),
    Language.HINDI: ("", "", "सच कहूँ तो ", "कुल मिलाकर ", "सबसे पहले, "),
    Language.FRENCH: ("", "", "Honnêtement, ", "Pour être juste, ", "Dans l'ensemble, "),
    Language.GERMAN: ("", "", "Ehrlich gesagt, ", "Insgesamt ", "Zunächst einmal, "),
    Language.SPANISH: ("", "", "Sinceramente, ", "En general, ", "Para ser justos, "),
}

CLOSERS: Final[dict[Language, tuple[str, ...]]] = {
    Language.ENGLISH: (
        "",
        "",
        " Would order again.",
        " Would not order again.",
        " Second time buying this.",
        " Been a customer for years.",
        " Hope this helps someone.",
        " Will update if anything changes.",
    ),
    Language.POLISH: (
        "",
        "",
        " Zamówię ponownie.",
        " Więcej nie zamówię.",
        " Kupuję drugi raz.",
        " Jestem klientem od lat.",
        " Mam nadzieję, że to pomoże.",
    ),
    Language.HINDI: (
        "",
        "",
        " फिर से ऑर्डर करूँगा।",
        " दोबारा नहीं लूँगा।",
        " यह दूसरी बार खरीदा है।",
        " कई सालों से ग्राहक हूँ।",
        " उम्मीद है यह मदद करेगा।",
    ),
    Language.FRENCH: (
        "",
        "",
        " Je commanderai à nouveau.",
        " Je ne recommanderai pas.",
        " C'est mon deuxième achat.",
        " Client depuis des années.",
        " J'espère que cela aidera.",
    ),
    Language.GERMAN: (
        "",
        "",
        " Ich bestelle wieder.",
        " Ich bestelle nicht noch einmal.",
        " Das ist mein zweiter Kauf.",
        " Seit Jahren Kunde.",
        " Ich hoffe, das hilft jemandem.",
    ),
    Language.SPANISH: (
        "",
        "",
        " Volveré a pedirlo.",
        " No volveré a comprarlo.",
        " Es mi segunda compra.",
        " Llevo años siendo cliente.",
        " Espero que sirva de ayuda.",
    ),
}


# Text in a language the platform does not claim to support. Used to generate
# records that should be detected and flagged as `unsupported`, proving the
# language pipeline degrades honestly rather than mislabelling them.
UNSUPPORTED_LANGUAGE_SAMPLES: Final[tuple[str, ...]] = (
    "Il prodotto è arrivato in ritardo e la confezione era danneggiata.",
    "O produto chegou atrasado e a embalagem estava danificada.",
    "Het product kwam te laat aan en de verpakking was beschadigd.",
    "Produkten kom for sent, og emballagen var beskadiget.",
)


def template_count() -> int:
    """Total number of distinct phrasings across all languages and topics."""
    return sum(
        len(phrasings)
        for bank in TEMPLATES.values()
        for by_sentiment in bank.values()
        for phrasings in by_sentiment.values()
    )
