# DEC-002: Algorithm Abstraction Layer with Registry Pattern

**Date:** 2025-12-27
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), PM (Alex), PO (Sam), QA Lead (Riley)

---

## Context

WTracker requires multiple algorithms for:
1. **Price forecasting** - Prophet (MVP), ARIMA, Monte Carlo (Phase 2+)
2. **Anomaly detection** - Z-score, velocity, Isolation Forest (Phase 2+)
3. **Trust scoring** - Bayesian reputation, velocity scoring

The project brief explicitly requires:
- Modular algorithm integration
- Algorithms should be swappable/testable independently
- Feature flags for algorithm rollout
- A/B testing capability for algorithm performance

We need an architecture that supports adding new algorithms without modifying existing code.

---

## Options Considered

### Option 1: Direct Implementation (No Abstraction)

**Description:** Implement each algorithm directly in service layer, call Prophet/Z-score by name.

**Pros:**
- Simplest initial implementation
- No abstraction overhead
- Fastest to write first algorithm

**Cons:**
- Tight coupling to specific implementations
- Cannot swap algorithms without code changes
- No standardized interface for testing
- A/B testing requires conditional logic everywhere
- Adding new algorithms touches existing code

**Evaluation:** Technical debt that will slow Phase 2+ development.

---

### Option 2: Strategy Pattern

**Description:** Define interface, pass algorithm instance to service.

**Pros:**
- Clean separation of algorithm from usage
- Easy to test with mocks
- Algorithms are independent

**Cons:**
- Caller must know which algorithm to use
- No central registry for discovery
- Configuration management scattered

**Evaluation:** Good pattern but missing registry for central management.

---

### Option 3: Registry Pattern with Abstract Base Classes

**Description:** Abstract base classes define contracts, registry manages instances, services use registry to get algorithms.

**Pros:**
- Centralized algorithm management
- Feature flags integrate naturally
- A/B testing via registry routing
- New algorithms plug in without touching existing code
- Type hints and IDE support via ABC
- Easy to list/discover available algorithms
- Configuration in one place

**Cons:**
- More upfront design work
- Slight runtime overhead for registry lookup
- Must define interfaces carefully upfront

**Evaluation:** Best balance of flexibility and maintainability.

---

### Option 4: Plugin System (Dynamic Loading)

**Description:** Algorithms as separate packages, discovered and loaded at runtime.

**Pros:**
- Maximum decoupling
- Can deploy new algorithms without restarting
- Third-party algorithm support

**Cons:**
- Significant complexity
- Security considerations for dynamic loading
- Harder to debug
- Overkill for internal-only algorithms

**Evaluation:** Over-engineered for our needs.

---

## Decision

**Selected: Registry Pattern with Abstract Base Classes**

We will implement:
1. Abstract base classes for each algorithm type (ForecastingAlgorithm, AnomalyDetector, TrustScorer)
2. A central AlgorithmRegistry that manages registration and retrieval
3. Configuration-driven selection of active algorithms
4. Feature flag integration for experimental algorithms

---

## Rationale

1. **Future extensibility:** New algorithms implement base class and register, no changes to services.

2. **Testability:** Mock algorithms implement same interface, easy to inject in tests.

3. **A/B testing:** Registry can route requests to different algorithms based on configuration.

4. **Feature flags:** Natural integration point - check flag before returning experimental algorithm.

5. **Discoverability:** Registry can list all available algorithms for admin dashboard.

6. **Type safety:** Abstract base classes provide IDE support and catch interface mismatches early.

7. **Fallback handling:** Registry can manage fallback logic (if Prophet fails, use SimpleAverage).

---

## Consequences

### Positive
- Clean separation between algorithm implementation and usage
- Easy to add Prophet, ARIMA, etc. without touching service code
- Can A/B test algorithms via configuration
- Testable with mock implementations
- Consistent error handling across all algorithms

### Negative
- Upfront design work to define interfaces
- Slight indirection in code (registry lookup vs direct call)
- Must ensure interfaces are stable (breaking changes affect all implementations)

### Neutral
- Learning curve for new developers (pattern is well-documented)
- Need to maintain registry configuration

---

## Implementation Details

### Base Interface Example

```python
class ForecastingAlgorithm(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def min_data_points(self) -> int:
        pass

    @abstractmethod
    def fit(self, prices: List[tuple[date, int]]) -> None:
        pass

    @abstractmethod
    def predict(self, horizon_days: List[int], confidence: float) -> List[ForecastResult]:
        pass
```

### Registry Example

```python
class AlgorithmRegistry:
    _forecasters: Dict[str, Type[ForecastingAlgorithm]] = {}

    @classmethod
    def register(cls, algo: Type[ForecastingAlgorithm]):
        cls._forecasters[algo.name] = algo

    @classmethod
    def get_active_forecaster(cls) -> ForecastingAlgorithm:
        return cls._forecasters[settings.ACTIVE_FORECASTER]()
```

### Configuration

```python
# Active algorithms controlled via environment/config
ACTIVE_FORECASTER = "prophet"  # or "simple_average", "arima"
ACTIVE_ANOMALY_DETECTORS = ["zscore", "velocity"]
```

---

## Related

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Full algorithm layer specification
- [2025-12-27-architecture-design.md](../MEETING_NOTES/2025-12-27-architecture-design.md) - Design discussion
