# Module Dependency Map

This diagram visualizes the relationships and data flow between the Variance Engine's core modules.

```mermaid
graph TD
    %% Infrastructure Layer
    subgraph Infrastructure
        CL[config_loader.py]
        MD[get_market_data.py]
        PP[portfolio_parser.py]
    end

    %% Model Layer
    subgraph Domain Models
        M_POS[models/position.py]
        M_CLUST[models/cluster.py]
        M_PORT[models/portfolio.py]
        M_ACT[models/actions.py]
        M_SPEC[models/specs.py]
    end

    %% Pattern Layer
    subgraph Pattern Layer
        S_BASE[strategies/base.py]
        S_FACT[strategies/factory.py]
        S_THETA[strategies/short_theta.py]
        M_MSPEC[models/market_specs.py]
    end

    %% Orchestration Layer
    subgraph Engines
        TE[triage_engine.py]
        VS[vol_screener.py]
        AP[analyze_portfolio.py]
    end

    %% Presentation Layer
    subgraph Presentation
        TUI[tui_renderer.py]
    end

    %% Dependencies
    CL --> MD
    CL --> TE
    CL --> VS
    
    PP --> M_POS
    M_POS --> M_CLUST
    M_CLUST --> M_PORT
    
    MD --> TE
    MD --> VS
    
    S_BASE --> S_THETA
    S_FACT --> S_BASE
    S_FACT --> S_THETA
    
    TE --> S_FACT
    TE --> M_ACT
    TE --> M_PORT
    
    VS --> M_MSPEC
    M_MSPEC --> M_SPEC
    
    AP --> TE
    AP --> VS
    
    TE --> TUI
    VS --> TUI
```

## Key Architectural Principles
1. **Unidirectional Flow:** Data moves from Ingest -> Domain -> Orchestration -> Presentation.
2. **Decoupled Mechanics:** Strategies (`ShortTheta`) are decoupled from the triage engine via the `StrategyFactory`.
3. **Modular Filtering:** Screener logic is decoupled from the search loop via the `Specification` pattern.
4. **Execution Isolation:** All actions flow through `ActionCommand` objects, which are read-only and lack execution capabilities.
