"""View-only search; it never changes findings, policies, or exports."""


def search_index(source, config, result):
    user_field = config.get("context", {}).get("User")
    unavailable = {
        f"{rule['name']}: rule input unavailable": rule["name"] for rule in config["rules"]
    }
    index = {}
    for record in result["records"]:
        values = [record["event_id"], record["session"]]
        if user_field:
            user = source.rows[record["row"] - 1].get(user_field)
            if user is not None:
                values.append(user)
        values.extend(item["name"] for item in record["evidence"] if item["kind"] == "rule")
        values.extend(unavailable[gap] for gap in record["gaps"] if gap in unavailable)
        # Separate values prevent a query from accidentally spanning two fields.
        index[record["row"]] = tuple(str(value).casefold() for value in values)
    return index


def matches(values, query):
    needle = query.strip().casefold()
    return not needle or any(needle in value for value in values)
