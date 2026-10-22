# Brevity bot fixtures

## AI blurb → short

Before:

```python
def is_enabled() -> bool:
    """Return True if the feature flag is enabled.

    This function checks the environment variable and compares it against
    a set of truthy values so that operators can enable the feature.
    """
    value = os.getenv("FLAG", "")
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    return False
```

After:

```python
def is_enabled() -> bool:
    return os.getenv("FLAG", "").strip().lower() in {"1", "true", "yes"}
```

## Do not drop a security fix

Security required redacting secrets. Illegal brevity (drops the fix):

```python
return {"GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY")}
```

Legal brevity (keeps redaction):

```python
return {"GEMINI_API_KEY": "***"} if os.environ.get("GEMINI_API_KEY") else {}
```
