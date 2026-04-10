"""
View Registry

Central registry for database view metadata. Provides a single source of truth
for what views exist, how they're structured, and how they relate to each other.

The registry is implemented as a lazy-loaded singleton to avoid circular imports
and enable easy testing (can create new instances).
"""

from typing import Dict, List, Optional, Set, Tuple
import logging

from app.views.models import ViewSchema, JoinRelationship

logger = logging.getLogger(__name__)


class ViewRegistry:
    """
    Manages metadata for all available database views.

    This registry serves as the foundation for Phase 1, providing agents with
    information about available data, column structure, and join relationships.

    Attributes:
        _views: Dictionary mapping view names to ViewSchema objects
        _joins: Dictionary mapping (source, target) tuples to JoinRelationship objects
        _views_by_domain: Dictionary mapping domain names to lists of view names
    """

    def __init__(self):
        """Initialize an empty view registry."""
        self._views: dict[str, ViewSchema] = {}
        self._joins: dict[Tuple[str, str], JoinRelationship] = {}
        self._views_by_domain: dict[str, List[str]] = {}

    def register_view(self, view: ViewSchema) -> None:
        """
        Register a view in the registry.

        Args:
            view: ViewSchema object to register

        Raises:
            ValueError: If view with same name already exists
        """
        if view.name in self._views:
            raise ValueError(f"View {view.name} already registered")

        self._views[view.name] = view

        # Index by domain
        if view.domain not in self._views_by_domain:
            self._views_by_domain[view.domain] = []
        self._views_by_domain[view.domain].append(view.name)

        logger.info(f"Registered view: {view.name} (domain: {view.domain})")

    def register_join(self, join: JoinRelationship) -> None:
        """
        Register a join relationship between two views.

        Args:
            join: JoinRelationship object to register

        Raises:
            ValueError: If join is invalid or views don't exist
        """
        # Validate the join relationship
        is_valid, error_msg = join.validate()
        if not is_valid:
            raise ValueError(f"Invalid join: {error_msg}")

        # Verify both views exist
        if join.source_view not in self._views:
            raise ValueError(f"Source view {join.source_view} not found in registry")
        if join.target_view not in self._views:
            raise ValueError(f"Target view {join.target_view} not found in registry")

        # Register the join (both directions)
        key = (join.source_view, join.target_view)
        self._joins[key] = join

        logger.info(
            f"Registered join: {join.source_view} → {join.target_view} "
            f"({join.relationship_type})"
        )

    def get_view(self, view_name: str) -> Optional[ViewSchema]:
        """
        Get a view by name.

        Args:
            view_name: Name of the view to retrieve

        Returns:
            ViewSchema if found, None otherwise
        """
        return self._views.get(view_name)

    def get_all_views(self) -> List[ViewSchema]:
        """
        Get all registered views.

        Returns:
            List of all ViewSchema objects
        """
        return list(self._views.values())

    def get_views_by_domain(self, domain: str) -> List[ViewSchema]:
        """
        Get all views in a specific domain.

        Args:
            domain: Domain name (sales, finance, operations, etc.)

        Returns:
            List of ViewSchema objects in that domain
        """
        view_names = self._views_by_domain.get(domain, [])
        return [self._views[name] for name in view_names]

    def get_all_domains(self) -> List[str]:
        """
        Get all registered domains.

        Returns:
            List of domain names
        """
        return list(self._views_by_domain.keys())

    def find_joins(self, view1: str, view2: str) -> Optional[JoinRelationship]:
        """
        Find a join relationship between two views.

        Args:
            view1: First view name
            view2: Second view name

        Returns:
            JoinRelationship if found, None otherwise
        """
        # Try both directions
        join = self._joins.get((view1, view2))
        if join:
            return join

        # Check reverse direction (though typically we'd have explicit joins)
        # For now, we don't auto-reverse joins
        return None

    def get_all_joins(self) -> List[JoinRelationship]:
        """
        Get all registered join relationships.

        Returns:
            List of all JoinRelationship objects
        """
        return list(self._joins.values())

    def validate_view_combination(self, view_names: List[str]) -> Tuple[bool, str]:
        """
        Validate that a combination of views can be queried together.

        For now, this checks:
        - All views exist in registry
        - If multiple views, they have join paths between them (basic check)

        Args:
            view_names: List of view names to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not view_names:
            return False, "Must specify at least one view"

        # Check all views exist
        for view_name in view_names:
            if view_name not in self._views:
                return False, f"View '{view_name}' not found in registry"

        # If only one view, always valid
        if len(view_names) == 1:
            return True, ""

        # For multiple views, check if they're related (simple check)
        # In Phase 3, this will do more sophisticated join path validation
        reachable = self.get_reachable_views(view_names[0])
        for view_name in view_names[1:]:
            if view_name not in reachable:
                return (
                    False,
                    f"View '{view_name}' is not reachable from '{view_names[0]}'",
                )

        return True, ""

    def find_join_path(self, from_view: str, to_view: str) -> Optional[List[str]]:
        """
        Find the shortest join path between two views using BFS.

        Args:
            from_view: Starting view name
            to_view: Target view name

        Returns:
            Ordered list of view names forming the join path (inclusive of both
            endpoints), or None if no path exists.
        """
        if from_view not in self._views or to_view not in self._views:
            return None

        if from_view == to_view:
            return [from_view]

        # BFS with parent tracking to reconstruct the path
        parents: Dict[str, Optional[str]] = {from_view: None}
        queue = [from_view]

        while queue:
            current = queue.pop(0)

            for (src, tgt) in self._joins:
                neighbor = None
                if src == current and tgt not in parents:
                    neighbor = tgt
                elif tgt == current and src not in parents:
                    neighbor = src

                if neighbor is not None:
                    parents[neighbor] = current
                    if neighbor == to_view:
                        # Reconstruct path
                        path = []
                        node: Optional[str] = to_view
                        while node is not None:
                            path.append(node)
                            node = parents[node]
                        return list(reversed(path))
                    queue.append(neighbor)

        return None

    def get_reachable_views(self, start_view: str) -> Set[str]:
        """
        Find all views reachable from a starting view via join relationships.

        Uses breadth-first search to find all connected views.

        Args:
            start_view: Starting view name

        Returns:
            Set of all reachable view names (including the start view)
        """
        if start_view not in self._views:
            return set()

        visited = {start_view}
        queue = [start_view]

        while queue:
            current = queue.pop(0)

            # Find all views this view can join to (both directions)
            for (src, tgt), _ in self._joins.items():
                if src == current and tgt not in visited:
                    visited.add(tgt)
                    queue.append(tgt)
                elif tgt == current and src not in visited:
                    visited.add(src)
                    queue.append(src)

        return visited

    def get_view_info(self, view_name: str) -> Optional[dict]:
        """
        Get comprehensive information about a view.

        Args:
            view_name: Name of the view

        Returns:
            Dictionary with view info and related joins, None if view not found
        """
        view = self.get_view(view_name)
        if not view:
            return None

        # Find joins involving this view
        incoming_joins = [
            join for (src, tgt), join in self._joins.items() if tgt == view_name
        ]
        outgoing_joins = [
            join for (src, tgt), join in self._joins.items() if src == view_name
        ]

        return {
            "view": view,
            "incoming_joins": incoming_joins,
            "outgoing_joins": outgoing_joins,
        }

    def __repr__(self) -> str:
        """String representation of the registry."""
        view_count = len(self._views)
        join_count = len(self._joins)
        domain_count = len(self._views_by_domain)
        return (
            f"ViewRegistry("
            f"views={view_count}, "
            f"joins={join_count}, "
            f"domains={domain_count})"
        )


# Global registry instance (lazy-loaded singleton)
_registry_instance: Optional[ViewRegistry] = None


def get_registry() -> ViewRegistry:
    """
    Get the global view registry instance (lazy-loaded singleton).

    The registry is created on first access and cached for subsequent calls.
    This avoids circular imports while providing a single shared instance.

    Returns:
        The global ViewRegistry instance
    """
    global _registry_instance

    if _registry_instance is None:
        _registry_instance = ViewRegistry()
        # Initialize with seed data
        from app.views.seed import initialize_registry

        initialize_registry(_registry_instance)
        logger.info("Initialized global view registry")

    return _registry_instance


def reset_registry() -> None:
    """
    Reset the global registry (useful for testing).

    This creates a fresh, empty registry.
    """
    global _registry_instance
    _registry_instance = None
    logger.info("Reset global view registry")


def create_test_registry() -> ViewRegistry:
    """
    Create a new independent registry for testing.

    This allows tests to have isolated registry instances without
    affecting the global singleton.

    Returns:
        A new ViewRegistry instance (not the global singleton)
    """
    registry = ViewRegistry()
    from app.views.seed import initialize_registry

    initialize_registry(registry)
    return registry
