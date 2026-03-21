# 🧭 MERIDIAN Quick Start Guide
## Intelligent Data Navigation Platform

### 5-Minute Setup + First Agent

*The True North for Your Data*

---

## 📋 Prerequisites

- Python 3.11+
- OpenAI API key (for GPT-4): https://platform.openai.com/api-keys
- PostgreSQL (optional, can mock database)

---

## ⚡ 5-Minute Setup

### Step 1: Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 2: Install Dependencies
```bash
pip install fastapi uvicorn langchain langchain-openai langraph pydantic sqlalchemy
```

### Step 3: Setup Environment
```bash
cat > .env << EOF
OPENAI_API_KEY=sk-your-key-here
LANGSMITH_API_KEY=lsv2_your-key-here  # Optional
LANGSMITH_PROJECT=meridian
EOF
```

### Step 4: Create Minimal App
```bash
mkdir -p app/views app/agents app/tools app/api
touch app/__init__.py app/main.py app/views/__init__.py app/agents/__init__.py app/tools/__init__.py
```

---

## 🚀 First MERIDIAN Agent (10 Minutes)

### Step 1: Create a Tool (Pydantic + Langchain)

**File: `app/tools/simple_tools.py`**

```python
from langchain.tools import tool
from langchain.pydantic_v1 import BaseModel, Field
from typing import List

class QueryInput(BaseModel):
    """Input for MERIDIAN query tool"""
    table: str = Field(..., description="Table to query (e.g., 'sales', 'customers')")
    limit: int = Field(default=10, description="Number of rows to return")

@tool(args_schema=QueryInput)
def query_database(table: str, limit: int = 10) -> dict:
    """
    Query database tables via MERIDIAN.
    
    Supports tables: sales, customers, products
    """
    # Mock data
    mock_data = {
        "sales": [
            {"id": 1, "customer": "Acme", "amount": 5000},
            {"id": 2, "customer": "TechCorp", "amount": 7500},
        ],
        "customers": [
            {"id": 1, "name": "Acme Corp", "segment": "Enterprise"},
            {"id": 2, "name": "TechCorp", "segment": "Mid-Market"},
        ]
    }
    
    return {
        "success": True,
        "table": table,
        "rows": mock_data.get(table, [])[:limit],
        "source": "MERIDIAN"
    }
```

### Step 2: Create Base MERIDIAN Agent

**File: `app/agents/simple_agent.py`**

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from app.tools.simple_tools import query_database

def create_sales_agent():
    """Create a MERIDIAN sales agent with intelligent navigation"""
    
    # Define prompt
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are MERIDIAN Sales Agent - part of the Meridian Intelligent Data Navigation Platform.

Your role: Navigate business data to deliver precise sales insights.

You can query sales and customer data using the available tools.
Be conversational and provide actionable insights based on data patterns.

When a user asks a question, navigate the data landscape to find the answer."""
        ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create LLM
    llm = ChatOpenAI(model="gpt-4", temperature=0.0)
    
    # Create agent
    agent = create_openai_tools_agent(
        llm,
        [query_database],  # MERIDIAN tool
        prompt
    )
    
    # Create executor
    executor = AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=[query_database],
        verbose=True,
        max_iterations=5
    )
    
    # Add memory for MERIDIAN state persistence
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )
    
    return executor, memory

def run_agent():
    """Run MERIDIAN Sales Agent"""
    executor, memory = create_sales_agent()
    
    # Get chat history
    chat_history = memory.buffer
    
    # Process user query - MERIDIAN navigates to the answer
    query = "What were our top sales this month?"
    
    print("🧭 MERIDIAN - Intelligent Data Navigation")
    print("=" * 50)
    print(f"Query: {query}\n")
    
    result = executor.invoke({
        "input": query,
        "chat_history": chat_history,
    })
    
    print(f"\n✨ Agent: {result['output']}")
    
    # Save to memory
    memory.save_context(
        {"input": query},
        {"output": result["output"]}
    )

if __name__ == "__main__":
    run_agent()
```

### Step 3: Run It!

```bash
python app/agents/simple_agent.py
```

**Output:**
```
🧭 MERIDIAN - Intelligent Data Navigation
==================================================
Query: What were our top sales this month?

I'll navigate the sales data to identify your top performers this month.

[Tool Call: query_database]
Table: sales
Limit: 10

Based on MERIDIAN's data navigation, your top sales this month are:
1. TechCorp: $7,500 ⭐
2. Acme Corp: $5,000

TechCorp is your leading revenue driver. These are your True North targets.
```

---

## 🔗 FastAPI Integration (10 Minutes)

**File: `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from app.agents.simple_agent import create_sales_agent

# MERIDIAN global state
agent_executor = None
memory = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Initialize MERIDIAN
    global agent_executor, memory
    agent_executor, memory = create_sales_agent()
    print("✅ MERIDIAN Agent initialized")
    
    yield
    
    # Shutdown
    print("🔌 MERIDIAN shutting down")

app = FastAPI(
    title="MERIDIAN - Intelligent Data Navigation",
    description="Navigate your database views with AI-powered precision",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    query: str
    response: str
    source: str = "MERIDIAN"

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "MERIDIAN",
        "version": "1.0.0"
    }

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Submit a query to MERIDIAN - navigate your data with intelligence"""
    
    result = agent_executor.invoke({
        "input": request.query,
        "chat_history": memory.buffer,
    })
    
    memory.save_context(
        {"input": request.query},
        {"output": result["output"]}
    )
    
    return QueryResponse(
        query=request.query,
        response=result["output"],
        source="MERIDIAN"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Run:**
```bash
python -m uvicorn app.main:app --reload
```

**Test:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me the top customers"}'
```

---

## 📊 Add Multiple Agents (MERIDIAN Orchestration with Langraph)

**File: `app/agents/orchestrator.py`**

```python
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from app.agents.simple_agent import create_sales_agent

class MeridianState(TypedDict):
    """MERIDIAN multi-agent workflow state"""
    query: str
    domain: str
    response: str

def build_meridian_orchestrator():
    """Build MERIDIAN multi-agent workflow"""
    
    workflow = StateGraph(MeridianState)
    
    # Router node - Navigate domain
    def router_node(state: MeridianState) -> dict:
        """MERIDIAN compass: Route query to appropriate domain"""
        query = state["query"].lower()
        
        if any(word in query for word in ["sales", "revenue", "customers"]):
            domain = "sales"
        elif any(word in query for word in ["finance", "budget", "cost"]):
            domain = "finance"
        else:
            domain = "sales"  # default
        
        print(f"🧭 MERIDIAN Compass: Routing to {domain.upper()} domain")
        return {**state, "domain": domain}
    
    # Sales handler
    def sales_handler(state: MeridianState) -> dict:
        """MERIDIAN Sales Agent"""
        executor, memory = create_sales_agent()
        result = executor.invoke({
            "input": state["query"],
            "chat_history": memory.buffer,
        })
        return {**state, "response": result["output"]}
    
    # Finance handler
    def finance_handler(state: MeridianState) -> dict:
        """MERIDIAN Finance Agent"""
        return {
            **state,
            "response": f"🧭 MERIDIAN Finance Agent: Processing '{state['query']}' (coming soon)"
        }
    
    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("sales", sales_handler)
    workflow.add_node("finance", finance_handler)
    
    # Set entry
    workflow.set_entry_point("router")
    
    # Routing logic
    def route_to_handler(state: MeridianState):
        if state["domain"] == "sales":
            return "sales"
        else:
            return "finance"
    
    workflow.add_conditional_edges(
        "router",
        route_to_handler,
        {"sales": "sales", "finance": "finance"}
    )
    
    # End nodes
    workflow.add_edge("sales", END)
    workflow.add_edge("finance", END)
    
    return workflow.compile()

# Test it
if __name__ == "__main__":
    workflow = build_meridian_orchestrator()
    
    result = workflow.invoke({
        "query": "What were our top sales?",
        "domain": None,
        "response": None,
    })
    
    print(f"\n🧭 MERIDIAN Domain: {result['domain']}")
    print(f"✨ Response: {result['response']}")
```

---

## 🔍 Enable Langsmith Observability for MERIDIAN

### Setup (1 minute)

```bash
# Get your API key from https://smith.langchain.com
export LANGSMITH_API_KEY=lsv2_your_key
export LANGSMITH_TRACING=true
export LANGSMITH_PROJECT=meridian
```

### That's it!

All MERIDIAN operations now auto-trace at: https://smith.langchain.com

---

## 🧪 Testing MERIDIAN

**File: `test_agent.py`**

```python
from app.agents.simple_agent import create_sales_agent

def test_meridian_agent():
    """Test MERIDIAN agent"""
    executor, memory = create_sales_agent()
    
    result = executor.invoke({
        "input": "Show sales data",
        "chat_history": memory.buffer,
    })
    
    assert "success" in result["output"].lower() or "data" in result["output"].lower()
    print("✅ MERIDIAN Test passed!")

if __name__ == "__main__":
    test_meridian_agent()
```

---

## 📁 File Structure After Setup

```
.
├── .env
├── app/
│   ├── __init__.py
│   ├── main.py                    # MERIDIAN FastAPI app
│   ├── tools/
│   │   ├── __init__.py
│   │   └── simple_tools.py        # MERIDIAN tools
│   └── agents/
│       ├── __init__.py
│       ├── simple_agent.py        # First MERIDIAN agent
│       └── orchestrator.py        # Multi-agent MERIDIAN workflow
└── test_agent.py
```

---

## 🎯 Next Steps

1. ✅ Run MERIDIAN simple agent
2. ✅ Test FastAPI endpoint
3. ✅ Add more MERIDIAN tools
4. ✅ Create second MERIDIAN agent
5. ✅ Build MERIDIAN orchestrator with Langraph
6. ✅ Enable Langsmith tracing
7. ✅ Follow the full MERIDIAN roadmap (MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md)

---

## 🔗 Key Concepts (MERIDIAN)

### Tool (`@tool` decorator)
Tools are MERIDIAN's navigation points - databases locations it can access.

### Agent (AgentExecutor)
Each agent is a MERIDIAN compass - knows its domain and how to navigate it.

### Memory (ConversationBufferMemory)
MERIDIAN's journey log - remembers previous navigation paths.

### Workflow (Langraph StateGraph)
MERIDIAN's constellation - multiple agents connected and coordinated.

---

## 🐛 Debugging MERIDIAN

### Enable verbose output
```python
executor = AgentExecutor(..., verbose=True)  # See MERIDIAN's thinking
```

### Check Langsmith
```bash
# View MERIDIAN traces at:
https://smith.langchain.com/o/YOUR_ORG/projects/meridian
```

### Print state in Langraph
```python
def handler_node(state):
    print(f"🧭 MERIDIAN State: {state}")
    return state
```

---

## 📚 Resources

- **Langchain Docs:** https://python.langchain.com
- **Langraph Tutorial:** https://langchain-ai.github.io/langgraph/
- **MERIDIAN Full Roadmap:** MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md
- **OpenAI Function Calling:** https://platform.openai.com/docs/guides/function-calling

---

## ❓ FAQ

**Q: How do I switch to a different LLM in MERIDIAN?**
MERIDIAN uses Langchain's LLM abstraction, so you can swap the model by replacing the `ChatOpenAI` instance in `app/config.py` with any Langchain-compatible LLM provider.

**Q: How do I add another tool to MERIDIAN?**
```python
@tool(args_schema=InputModel)
def new_tool(arg1: str) -> dict:
    """New navigation point for MERIDIAN"""
    return {"result": "..."}

# Add to agent:
tools = [query_database, new_tool]
agent = create_openai_tools_agent(llm, tools, prompt)
```

**Q: How do I persist MERIDIAN memory between sessions?**
```python
# Use RedisChatMessageHistory or other backends:
from langchain_community.chat_message_histories import RedisChatMessageHistory

memory = ConversationBufferMemory(
    chat_memory=RedisChatMessageHistory(session_id="user123"),
    memory_key="chat_history",
)
```

**Q: How do I stream MERIDIAN responses?**
```python
result = executor.invoke(
    {"input": query},
    stream_mode="values"
)
for chunk in result:
    print(chunk["output"], end="", flush=True)
```

---

---

**MERIDIAN v1.0**  
**Last Updated:** March 19, 2026  
**Status:** Ready to navigate! 🧭

*The True North for Your Data*

Happy building! 🚀
