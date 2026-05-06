from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Default pagination with page_size override via query param.

    This ensures list endpoints never return the full dataset accidentally
    and lets clients specify ?page_size= to a safe maximum.
    """

    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


