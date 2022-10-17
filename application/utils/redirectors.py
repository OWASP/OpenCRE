def cwe_redirector(cwe_id: int):
    return f"https://cwe.mitre.org/data/definitions/{cwe_id}.html"


def capec_redirector(capec_id: int) -> str:
    return f"https://capec.mitre.org/data/definitions/{capec_id}.html"


def redirect(node_type, node_id):
    if node_type.lower() == "cwe":
        return cwe_redirector(node_id)
    elif node_type.lower() == "capec":
        return capec_redirector(node_id)
