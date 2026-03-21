"""
Result Pagination and Streaming

Handles pagination of large query results with configurable page sizes,
cursor-based navigation, and streaming support.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from math import ceil

logger = logging.getLogger(__name__)


class PaginationConfig:
    """Configuration for pagination."""

    def __init__(
        self,
        default_page_size: int = 100,
        max_page_size: int = 10000,
        min_page_size: int = 1,
    ):
        self.default_page_size = default_page_size
        self.max_page_size = max_page_size
        self.min_page_size = min_page_size

    def validate_page_size(self, page_size: int) -> int:
        """Validate and clamp page size to allowed range."""
        return max(
            self.min_page_size,
            min(page_size, self.max_page_size)
        )


class PaginatedResult:
    """Represents a paginated result set."""

    def __init__(
        self,
        rows: List[Dict[str, Any]],
        page: int,
        page_size: int,
        total_rows: int,
    ):
        self.rows = rows
        self.page = page
        self.page_size = page_size
        self.total_rows = total_rows
        self.total_pages = ceil(total_rows / page_size) if page_size > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "data": self.rows,
            "pagination": {
                "page": self.page,
                "page_size": self.page_size,
                "total_rows": self.total_rows,
                "total_pages": self.total_pages,
                "has_next": self.page < self.total_pages,
                "has_previous": self.page > 1,
            }
        }

    @property
    def offset(self) -> int:
        """Calculate offset for SQL LIMIT/OFFSET."""
        return (self.page - 1) * self.page_size

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1

    @property
    def next_page(self) -> Optional[int]:
        """Get next page number."""
        return self.page + 1 if self.has_next else None

    @property
    def previous_page(self) -> Optional[int]:
        """Get previous page number."""
        return self.page - 1 if self.has_previous else None


class Paginator:
    """Handles pagination of result sets."""

    def __init__(self, config: Optional[PaginationConfig] = None):
        self.config = config or PaginationConfig()

    def paginate(
        self,
        rows: List[Dict[str, Any]],
        page: int = 1,
        page_size: Optional[int] = None,
    ) -> PaginatedResult:
        """Paginate a result set.

        Args:
            rows: Complete result set
            page: Page number (1-indexed)
            page_size: Rows per page (uses default if None)

        Returns:
            PaginatedResult with requested page
        """
        if page_size is None:
            page_size = self.config.default_page_size

        page_size = self.config.validate_page_size(page_size)

        # Validate page number
        total_rows = len(rows)
        total_pages = ceil(total_rows / page_size) if page_size > 0 else 0

        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages

        # Get page data
        offset = (page - 1) * page_size
        end = offset + page_size
        page_data = rows[offset:end]

        logger.debug(
            f"Paginated result: page {page}/{total_pages}, "
            f"rows {offset}-{end} of {total_rows}"
        )

        return PaginatedResult(
            rows=page_data,
            page=page,
            page_size=page_size,
            total_rows=total_rows,
        )

    def paginate_with_limit(
        self,
        rows: List[Dict[str, Any]],
        limit: int,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Paginate using LIMIT/OFFSET style.

        Args:
            rows: Complete result set
            limit: Maximum rows to return
            offset: Starting row offset

        Returns:
            Tuple of (page_rows, pagination_info)
        """
        total_rows = len(rows)
        limit = self.config.validate_page_size(limit)

        if offset < 0:
            offset = 0
        elif offset >= total_rows:
            offset = total_rows - 1 if total_rows > 0 else 0

        end = min(offset + limit, total_rows)
        page_data = rows[offset:end]

        pagination_info = {
            "offset": offset,
            "limit": limit,
            "returned_rows": len(page_data),
            "total_rows": total_rows,
            "has_more": end < total_rows,
        }

        return page_data, pagination_info

    def get_page_bounds(
        self,
        page: int,
        page_size: int,
    ) -> Tuple[int, int]:
        """Get start and end row numbers for a page.

        Args:
            page: Page number (1-indexed)
            page_size: Rows per page

        Returns:
            Tuple of (start_row, end_row)
        """
        page_size = self.config.validate_page_size(page_size)
        start = (page - 1) * page_size
        end = start + page_size
        return start, end

    def calculate_total_pages(
        self,
        total_rows: int,
        page_size: int,
    ) -> int:
        """Calculate total number of pages.

        Args:
            total_rows: Total number of rows
            page_size: Rows per page

        Returns:
            Total number of pages
        """
        page_size = self.config.validate_page_size(page_size)
        return ceil(total_rows / page_size) if page_size > 0 else 0


class StreamingResult:
    """Generator-based streaming result for large datasets."""

    def __init__(
        self,
        rows: List[Dict[str, Any]],
        chunk_size: int = 1000,
    ):
        """Initialize streaming result.

        Args:
            rows: Complete result set
            chunk_size: Number of rows per chunk
        """
        self.rows = rows
        self.chunk_size = chunk_size
        self.total_rows = len(rows)
        self.chunks_yielded = 0

    def __iter__(self):
        """Iterate over chunks of results."""
        for i in range(0, len(self.rows), self.chunk_size):
            chunk = self.rows[i : i + self.chunk_size]
            self.chunks_yielded += 1
            yield chunk

    def to_stream_response(self) -> Dict[str, Any]:
        """Get response metadata for streaming response."""
        return {
            "total_rows": self.total_rows,
            "chunk_size": self.chunk_size,
            "total_chunks": ceil(self.total_rows / self.chunk_size),
        }
