import os

# QUERY/DECOMPOSE are default-on in production and would call the helper model from
# every router test that reaches comprehension. These tests mock their LLMs, so pin
# the two flags off for the package (a test can still opt in via environ_override).
for _flag in ("OWASP_CX_QUERY", "OWASP_CX_DECOMPOSE"):
    os.environ.setdefault(_flag, "0")
