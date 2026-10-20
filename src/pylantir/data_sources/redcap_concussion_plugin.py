"""REDCap data source for the CPIP concussion study."""

from .redcap_plugin import REDCapPlugin


class ConcussionREDCapPlugin(REDCapPlugin):
    """Use the standard REDCap workflow with concussion-study credentials."""

    API_URL_ENV = "REDCAP_API_URL_CONCUSSION"
    API_TOKEN_ENV = "REDCAP_API_TOKEN_CONCUSSION"

    def get_source_name(self) -> str:
        """Return the concussion REDCap source identifier."""
        return "REDCap Concussion"
