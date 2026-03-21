"""
Database Index Optimizer

Analyzes query patterns and recommends indexes for optimization.
Tracks slow queries and suggests optimal indexing strategies.
"""

import logging
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class QueryPattern:
    """Represents a query access pattern."""
    table: str
    columns: List[str]  # Columns in WHERE/JOIN conditions
    frequency: int = 1
    avg_execution_time_ms: float = 0.0
    last_seen: Optional[datetime] = None


@dataclass
class IndexRecommendation:
    """Index recommendation."""
    table: str
    columns: List[str]
    index_name: str
    estimated_benefit: str  # "HIGH", "MEDIUM", "LOW"
    reason: str
    priority: int  # 1-10, higher = more important

    def to_sql(self) -> str:
        """Generate CREATE INDEX SQL."""
        col_str = ", ".join(self.columns)
        return f"CREATE INDEX {self.index_name} ON {self.table} ({col_str});"


class QueryAnalyzer:
    """Analyzes query patterns to identify indexing opportunities."""

    def __init__(self):
        self.patterns: Dict[str, QueryPattern] = {}
        self.slow_queries: List[Dict[str, Any]] = []
        self.slow_query_threshold_ms = 100.0

    def record_query(
        self,
        table: str,
        columns: List[str],
        execution_time_ms: float,
    ) -> None:
        """Record query execution for analysis.

        Args:
            table: Table name
            columns: Columns accessed in WHERE/JOIN
            execution_time_ms: Query execution time
        """
        # Create pattern key
        pattern_key = f"{table}:{','.join(sorted(columns))}"

        if pattern_key in self.patterns:
            pattern = self.patterns[pattern_key]
            pattern.frequency += 1
            # Update average execution time
            old_avg = pattern.avg_execution_time_ms
            pattern.avg_execution_time_ms = (
                (old_avg * (pattern.frequency - 1) + execution_time_ms)
                / pattern.frequency
            )
        else:
            pattern = QueryPattern(
                table=table,
                columns=columns,
                frequency=1,
                avg_execution_time_ms=execution_time_ms,
            )
            self.patterns[pattern_key] = pattern

        pattern.last_seen = datetime.utcnow()

        # Track slow queries
        if execution_time_ms > self.slow_query_threshold_ms:
            self.slow_queries.append({
                "table": table,
                "columns": columns,
                "execution_time_ms": execution_time_ms,
                "timestamp": datetime.utcnow().isoformat(),
            })

            # Keep only recent slow queries
            if len(self.slow_queries) > 1000:
                self.slow_queries = self.slow_queries[-500:]

    def get_recommendations(self) -> List[IndexRecommendation]:
        """Generate index recommendations based on patterns.

        Returns:
            List of recommended indexes, sorted by priority
        """
        recommendations = []
        existing_indexes = set()

        # Analyze each pattern
        for pattern in self.patterns.values():
            # Skip if columns are low-value
            if not pattern.columns or len(pattern.columns) == 0:
                continue

            # Single column indexes for high-frequency access
            if pattern.frequency > 10 and pattern.avg_execution_time_ms > 50:
                for col in pattern.columns[:2]:  # Limit to first 2 columns
                    index_name = f"idx_{pattern.table}_{col}"

                    if index_name not in existing_indexes:
                        recommendations.append(IndexRecommendation(
                            table=pattern.table,
                            columns=[col],
                            index_name=index_name,
                            estimated_benefit="HIGH" if pattern.frequency > 50 else "MEDIUM",
                            reason=f"Frequently accessed ({pattern.frequency} times, "
                                   f"avg {pattern.avg_execution_time_ms:.1f}ms)",
                            priority=min(10, pattern.frequency // 10),
                        ))
                        existing_indexes.add(index_name)

            # Composite index for multi-column access patterns
            if (len(pattern.columns) > 1 and pattern.frequency > 5 and
                pattern.avg_execution_time_ms > 100):

                col_str = "_".join(pattern.columns[:3])  # Limit to first 3 columns
                index_name = f"idx_{pattern.table}_{col_str}"

                if index_name not in existing_indexes:
                    recommendations.append(IndexRecommendation(
                        table=pattern.table,
                        columns=pattern.columns[:3],
                        index_name=index_name,
                        estimated_benefit="HIGH",
                        reason=f"Multi-column composite access pattern "
                               f"({pattern.frequency} times, "
                               f"avg {pattern.avg_execution_time_ms:.1f}ms)",
                        priority=min(10, pattern.frequency // 5),
                    ))
                    existing_indexes.add(index_name)

        # Sort by priority
        recommendations.sort(key=lambda r: r.priority, reverse=True)
        return recommendations[:20]  # Return top 20 recommendations

    def get_slow_query_summary(self) -> Dict[str, Any]:
        """Get summary of slow queries.

        Returns:
            Summary statistics
        """
        if not self.slow_queries:
            return {
                "slow_query_count": 0,
                "slowest_tables": [],
            }

        # Group by table
        table_stats = defaultdict(lambda: {"count": 0, "max_time": 0})
        for query in self.slow_queries:
            table = query["table"]
            table_stats[table]["count"] += 1
            table_stats[table]["max_time"] = max(
                table_stats[table]["max_time"],
                query["execution_time_ms"],
            )

        # Sort by count
        slowest_tables = sorted(
            table_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )

        return {
            "slow_query_count": len(self.slow_queries),
            "slowest_tables": [
                {
                    "table": table,
                    "count": stats["count"],
                    "max_time_ms": stats["max_time"],
                }
                for table, stats in slowest_tables[:10]
            ],
        }

    def get_pattern_summary(self) -> Dict[str, Any]:
        """Get summary of query patterns.

        Returns:
            Summary statistics
        """
        if not self.patterns:
            return {
                "total_patterns": 0,
                "total_queries": 0,
                "tables": [],
            }

        total_queries = sum(p.frequency for p in self.patterns.values())
        table_patterns = defaultdict(list)

        for pattern in self.patterns.values():
            table_patterns[pattern.table].append(pattern)

        return {
            "total_patterns": len(self.patterns),
            "total_queries": total_queries,
            "tables": [
                {
                    "table": table,
                    "patterns": len(patterns),
                    "total_accesses": sum(p.frequency for p in patterns),
                }
                for table, patterns in sorted(
                    table_patterns.items(),
                    key=lambda x: sum(p.frequency for p in x[1]),
                    reverse=True,
                )[:10]
            ],
        }


class IndexOptimizer:
    """Main index optimization coordinator."""

    def __init__(self):
        self.analyzer = QueryAnalyzer()

    def analyze_workload(self) -> Dict[str, Any]:
        """Analyze current workload and provide recommendations.

        Returns:
            Analysis results including recommendations
        """
        recommendations = self.analyzer.get_recommendations()
        slow_summary = self.analyzer.get_slow_query_summary()
        pattern_summary = self.analyzer.get_pattern_summary()

        return {
            "recommendations": [
                {
                    "table": r.table,
                    "columns": r.columns,
                    "index_name": r.index_name,
                    "sql": r.to_sql(),
                    "benefit": r.estimated_benefit,
                    "reason": r.reason,
                    "priority": r.priority,
                }
                for r in recommendations
            ],
            "slow_queries": slow_summary,
            "pattern_analysis": pattern_summary,
        }

    def get_query_plan_tips(self, table: str) -> List[str]:
        """Get optimization tips for a specific table.

        Args:
            table: Table name

        Returns:
            List of optimization tips
        """
        tips = []

        # Find patterns for this table
        table_patterns = [
            p for p in self.analyzer.patterns.values()
            if p.table == table
        ]

        if not table_patterns:
            return ["No query patterns recorded for this table yet."]

        # Analyze patterns
        total_accesses = sum(p.frequency for p in table_patterns)
        avg_time = sum(
            p.avg_execution_time_ms * p.frequency for p in table_patterns
        ) / total_accesses

        if avg_time > 200:
            tips.append(
                "⚠️ Queries on this table are slow (avg > 200ms). "
                "Consider adding indexes on frequently accessed columns."
            )

        if total_accesses > 100:
            tips.append(
                "✓ High access frequency detected. "
                "Ensure appropriate indexes are in place."
            )

        # Multi-column access patterns
        multi_col_patterns = [p for p in table_patterns if len(p.columns) > 1]
        if multi_col_patterns:
            cols = multi_col_patterns[0].columns
            tips.append(
                f"💡 Consider composite index on ({', '.join(cols)}) "
                f"for multi-column queries."
            )

        return tips
