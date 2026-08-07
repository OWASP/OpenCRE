import requests

from dataclasses import dataclass
from .models import CRE


@dataclass
class OpenCREConfig:
    """
    Configuration class for OpenCRE.

    Attributes:
    - HOST_URL (str): The base URL for OpenCRE.
    - API_PREFIX (str): The API prefix for OpenCRE.
    """
    HOST_URL: str = "https://www.opencre.org/"
    API_PREFIX: str = "rest/v1/"


class OpenCRE:
    """
    OpenCRE class for interacting with the OpenCRE API.

    Methods:
    - __init__(self): Initializes an OpenCRE instance with default configuration.
    - get_endpoint_url(self, endpoint_title: str): Generates the full URL for a given API endpoint title.
    - perform_api_get_request(self, endpoint_title: str): Performs a GET request to the specified API endpoint.
    - root_cres(self) -> list[CRE]: Retrieves a list of root CREs from the API.
    - cre(self, cre_id: str) -> CRE | None: Retrieves information about a specific CRE identified by cre_id.

    Attributes:
    - conf (OpenCREConfig): Configuration object containing OpenCRE settings.
    """
    def __init__(self):
        """
        Initializes an OpenCRE instance with default configuration.
        """
        self.conf = OpenCREConfig()

    def get_endpoint_url(self, endpoint_title: str):
        """
        Generates the full URL for a given API endpoint title.

        Parameters:
        - endpoint_title (str): The title of the API endpoint.

        Returns:
        str: The full URL for the specified API endpoint.
        """
        host_url = self.conf.HOST_URL
        api_prefix = self.conf.API_PREFIX
        endpoint_url = f'{host_url}{api_prefix}{endpoint_title}'
        return endpoint_url

    def perform_api_get_request(self, endpoint_title: str):
        """
        Performs a GET request to the specified API endpoint.

        Parameters:
        - endpoint_title (str): The title of the API endpoint.

        Returns:
        requests.Response | None: The response object for the GET request, or None if the endpoint is not found.
        """
        endpoint_url = self.get_endpoint_url(endpoint_title=endpoint_title)
        response = requests.get(url=endpoint_url)

        if response.status_code == 404:
            return None

        return response

    def root_cres(self) -> list[CRE]:
        """
        Retrieves a list of root CREs from the API.

        Returns:
        list[CRE]: A list of CRE objects representing root CREs.
        """
        endpoint_title = "root_cres"
        root_cres_response = self.perform_api_get_request(endpoint_title)
        cres = CRE.parse_from_response(response=root_cres_response, many=True)
        return cres

    def cre(self, cre_id: str) -> CRE | None:
        """
        Retrieves information about a specific CRE identified by cre_id.

        Parameters:
        - cre_id (str): The identifier of the CRE.

        Returns:
        CRE | None: A CRE object if the CRE is found, or None if not found.
        """
        endpoint_title = f"id/{cre_id}"

        if not isinstance(cre_id, str):
            raise TypeError("Expected type str")

        cre_response = self.perform_api_get_request(endpoint_title)

        if cre_response is None:
            return None

        cre = CRE.parse_from_response(response=cre_response)
        return cre
