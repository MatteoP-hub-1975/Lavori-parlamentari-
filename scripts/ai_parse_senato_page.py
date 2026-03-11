def validate_items(items, target_date_str: str):

    allowed_categories = {
        "Non attinenti",
        "Interesse industriale generale",
        "Interesse industria del trasporto",
        "Interesse trasporto marittimo",
    }

    normalized = []

    for item in items:

        if not isinstance(item, dict):
            continue

        if is_excluded_organ(item):
            continue

        normalized_item = {
            "ramo": "Senato",
            "data_pubblicazione": target_date_str,
            "sezione": compact_spaces(str(item.get("sezione", ""))),
            "tipo_atto": compact_spaces(str(item.get("tipo_atto", ""))),
            "numero": compact_spaces(str(item.get("numero", ""))),
            "titolo": compact_spaces(str(item.get("titolo", ""))),
            "commissione": compact_spaces(str(item.get("commissione", ""))),
            "seduta": compact_spaces(str(item.get("seduta", ""))),
            "link_pdf": compact_spaces(str(item.get("link_pdf", ""))),
            "categoria_preliminare": compact_spaces(str(item.get("categoria_preliminare", ""))),
            "motivazione_preliminare": compact_spaces(str(item.get("motivazione_preliminare", ""))),
            "richiede_lettura_pdf": bool(item.get("richiede_lettura_pdf", False)),
        }

        if normalized_item["categoria_preliminare"] not in allowed_categories:
            normalized_item["categoria_preliminare"] = "Non attinenti"

        normalized.append(normalized_item)

    return normalized