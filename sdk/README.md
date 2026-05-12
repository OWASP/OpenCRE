# OpenCRE SDK

The OpenCRE SDK is a Python (3.11 and later) library that provides a convenient interface for interacting with the OpenCRE API. It includes classes for handling Common Requirements Enumeration (CRE) data, links, and associated documents.


## Installation

```bash
pip install opencre-sdk
```

## Usage


### Create an OpenCRE instance

```python
from opencre import OpenCRE

# Initialize OpenCRE SDK
opencre = OpenCRE()
```

### Configuration
The `OpenCREConfig` class allows you to configure the OpenCRE SDK with your specific settings. By default, it is configured with the OpenCRE base URL and API prefix.

```python
from opencre_sdk import OpenCREConfig, OpenCRE

# Create an OpenCRE configuration instance
config = OpenCREConfig()

# Optionally, customize the configuration
config.HOST_URL = "https://example.org/"
config.API_PREFIX = "custom/v1/"

# Create an OpenCRE instance with the custom configuration
opencre = OpenCRE(config=config)
```

## Interacting with CREs

The `OpenCRE` class provides methods for interacting with CREs:

### Retrieving Root CREs

To retrieve a list of root CREs:

```python
root_cres = opencre.root_cres()
print(root_cres)
```

### Retrieve a specific CRE by ID

```python
cre_id = "170-772"
cre = opencre.cre(cre_id)
print(str(cre))  # Outputs: 'CRE 170-772'
print(cre.name)  # Outputs: 'Cryptography'
print(cre.id)    # Outputs: '170-772'
```

## Handling Links and Documents

The `Link` class represents a link associated with a CRE, and the `Document` class represents a document associated with a CRE. Additional document types (`Standard`, `Tool`, and `CRELink`) extend the `Document` class.

### Access links of a CRE

```python
cre = opencre.cre("170-772")
links = cre.links
link = links[5]
print(link.ltype)  # Outputs: 'Linked To'
doc = link.document
print(doc.name)   # Outputs: 'Cloud Controls Matrix'
```

#### Link Types (ltype)

`ltype` attribute in the `Link` class represents the type of relationship between the CRE and the linked document. Currently, there are two possible values for ltype:

- **`Contains`**: This indicates that the CRE ncludes the content of the linked document. For instance, a CRE about "Manual penetration testing" might contain another CRE about "Dynamic security testing".

- **`Linked To`**: This signifies a reference to an external standard, tool, or another CRE. For example, a CRE might be linked to a specific section in the "NIST SSDF" standard.

## Contributing

We welcome contributions! Please submit pull requests for bug fixes, features, and improvements. See [**Contributing**](https://github.com/OWASP/OpenCRE/blob/main/CONTRIBUTING.md) for contributing instructions.
