# MERIDIAN Documentation

Welcome to the MERIDIAN project documentation.

## Quick Navigation

### Getting Started
- [Setup Guide](SETUP.md) - Local development environment setup
- [Quick Start](../docs/examples/quickstart.md) - Your first agent query

### Core Concepts
- [Architecture](ARCHITECTURE.md) - System design & components
- [Agents Overview](agents/README.md) - Understanding domain agents
- [Views System](views/README.md) - Data metadata & relationships
- [API Documentation](API.md) - REST API endpoints

### Implementation
- [Phase 1: View Registry](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md#phase-1) - Building the metadata layer
- [Phase 2: First Agent](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md#phase-2) - Single agent implementation
- [Phase 3: Query Safety](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md#phase-3) - Validation & security
- [Phase 4: Multi-Agent](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md#phase-4) - Orchestration with Langraph
- [Phase 5: Production](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md#phase-5) - Hardening & deployment

### Domain Guides
- [Sales Agent](agents/sales_agent.md) - Revenue analysis queries
- [Finance Agent](agents/finance_agent.md) - Ledger & accounting queries
- [Operations Agent](agents/operations_agent.md) - Logistics & inventory queries

### Reference
- [View Catalog](views/view_catalog.md) - All available database views
- [Join Relationships](views/join_relationships.md) - How views connect
- [API Reference](API.md) - Complete endpoint documentation
- [Contributing](CONTRIBUTING.md) - Development guidelines
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues & solutions

## Key Directories

```
docs/
├── README.md              # This file
├── SETUP.md              # Setup instructions
├── ARCHITECTURE.md       # System architecture
├── API.md                # API documentation
├── DEPLOYMENT.md         # Deployment guide
├── CONTRIBUTING.md       # Contribution guide
├── TROUBLESHOOTING.md    # Troubleshooting
│
├── agents/
│   ├── README.md         # Agent system overview
│   ├── sales_agent.md    # Sales agent details
│   ├── finance_agent.md  # Finance agent details
│   └── operations_agent.md # Operations agent details
│
├── views/
│   ├── README.md         # View system overview
│   ├── view_catalog.md   # All available views
│   └── join_relationships.md # Join rules
│
└── examples/
    ├── quickstart.md     # Quick start examples
    ├── agent_examples.py # Code examples
    └── queries.md        # Sample queries
```

## Starting Points by Role

### For Developers
1. Read [SETUP.md](SETUP.md) - Get your environment ready
2. Follow [Quick Start](examples/quickstart.md) - Run your first agent
3. Explore [Architecture](ARCHITECTURE.md) - Understand the system
4. Dive into [Phase implementation guides](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md)

### For Architects
1. Read [ARCHITECTURE.md](ARCHITECTURE.md) - System design
2. Review [Agents Overview](agents/README.md) - Agent patterns
3. Check [Views System](views/README.md) - Data architecture
4. Study the [Phase breakdown](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md)

### For Product/Business
1. Review the [Executive Summary](../MERIDIAN_EXECUTIVE_SUMMARY.md)
2. Understand [API Documentation](API.md) - What developers can build
3. Check [Example Queries](examples/queries.md) - What users can ask

## Project Status

**Version:** 0.1.0
**Status:** In Development (Phase 1-2)
**Last Updated:** [Current Date]

---

**Ready to get started?** → [Setup Guide](SETUP.md)
