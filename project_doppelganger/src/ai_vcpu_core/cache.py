import time
import random
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, Generic, TypeVar

from .config import CacheConfig

T = TypeVar('T') # Generic type for cache entry data

@dataclass
class CacheEntry(Generic[T]):
    key: str
    data: T
    timestamp: float = field(default_factory=time.time)
    # Add other metadata like frequency, expiry, etc. if needed

class BaseCache(Generic[T]):
    """Base class for a cache level."""
    def __init__(self, config: CacheConfig, name_suffix: str = ""):
        self.config = config
        self.name = config.name + name_suffix
        # Using OrderedDict for LRU behavior: most recently used at the end.
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._max_entries = (config.size_kb * 1024) // 128 # Approximate entries, assuming 128 bytes/entry (very rough)
        if self._max_entries == 0: self._max_entries = 1 # Ensure cache can hold at least one entry

        self.hits = 0
        self.misses = 0
        self.evictions = 0

        # For simulation of latency
        self._simulated_processing_time_ns = 0

    def _evict_if_needed(self):
        while len(self._cache) >= self._max_entries: # Use >= to make space before adding new one
            old_key, _ = self._cache.popitem(last=False) # Pop oldest (LRU)
            self.evictions += 1
            # print(f"DEBUG: {self.name} evicted {old_key}")


    def read(self, key: str) -> Optional[CacheEntry[T]]:
        self._simulated_processing_time_ns += self.config.latency_ns
        if key in self._cache:
            self.hits += 1
            entry = self._cache[key]
            entry.timestamp = time.time() # Update timestamp on access
            self._cache.move_to_end(key) # Mark as recently used
            return entry
        else:
            self.misses += 1
            return None

    def write(self, key: str, data: T) -> CacheEntry[T]:
        self._simulated_processing_time_ns += self.config.latency_ns # Write also incurs latency
        if key in self._cache:
            # Update existing entry
            self._cache[key].data = data
            self._cache[key].timestamp = time.time()
            self._cache.move_to_end(key)
        else:
            self._evict_if_needed()
            new_entry = CacheEntry(key=key, data=data)
            self._cache[key] = new_entry
        return self._cache[key]

    def invalidate(self, key: str):
        if key in self._cache:
            del self._cache[key]
            # print(f"DEBUG: {self.name} invalidated {key}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "size_kb": self.config.size_kb,
            "max_entries": self._max_entries,
            "current_entries": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": (self.hits / (self.hits + self.misses)) if (self.hits + self.misses) > 0 else 0,
            "simulated_processing_time_ns": self._simulated_processing_time_ns
        }

    def flush(self):
        self._cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self._simulated_processing_time_ns = 0
        # print(f"DEBUG: {self.name} flushed.")

# Specific Cache Level Implementations (can be simple aliases or add specific logic)
class L1Cache(BaseCache[Any]):
    def __init__(self, config: CacheConfig, core_id: int):
        super().__init__(config, name_suffix=f"_Core{core_id}")

class L2Cache(BaseCache[Any]):
    pass

class L3Cache(BaseCache[Any]):
    pass

class HolographicMemoryCache(BaseCache[Any]): # Conceptually very large and slower
    def __init__(self, config: CacheConfig):
        super().__init__(config)
        # Holographic memory might have different eviction or storage properties
        # For now, it behaves like a large BaseCache

class ContextSpecificCacheLayer(BaseCache[Any]):
    """A cache layer designed for specific types of contextual data."""
    def __init__(self, config: CacheConfig):
        super().__init__(config)
        # May have specialized methods for structured context data, e.g., conversation turns

class CacheHierarchy:
    """Manages the hierarchy of caches for a core or the vCPU."""
    def __init__(self, config: "AIVCPUConfig", core_id: Optional[int] = None): # Forward reference for AIVCPUConfig
        self.config = config
        self.core_id = core_id # If None, this hierarchy is for shared caches (L2/L3)

        self.l1: Optional[L1Cache] = None
        if core_id is not None:
            core_conf = next((c for c in config.specialized_core_configs if c.core_id == core_id), None)
            if not core_conf: # Try to find a general core config (not explicitly listed in specialized_core_configs)
                 # This assumes general cores also have an L1 defined by a default CoreConfig.
                 # For simplicity, we'll use the L1 config from the first specialized core if available,
                 # or a default L1CacheConfig if no specialized cores are defined.
                 # This part needs refinement if general cores have different L1s.
                l1_config = config.specialized_core_configs[0].l1_cache_config if config.specialized_core_configs else CacheConfig("L1_Default",64,1.0)
            else:
                l1_config = core_conf.l1_cache_config
            self.l1 = L1Cache(l1_config, core_id)

        # Shared caches (these would typically be single instances shared by cores)
        # For simulation, each hierarchy object might get its own instance, or they could be passed in.
        # Let's assume they are passed in or globally managed if true sharing is modeled.
        # For now, each hierarchy creates its own conceptual L2/L3.
        self.l2: L2Cache = L2Cache(config.l2_cache_config)
        self.l3: Optional[L3Cache] = L3Cache(config.l3_cache_config) if config.l3_cache_config else None

        self.holographic_memory: HolographicMemoryCache = HolographicMemoryCache(config.holographic_memory_config)

        self.context_caches: Dict[str, ContextSpecificCacheLayer] = {}
        for csl_config in config.context_specific_cache_layers_config:
            self.context_caches[csl_config.name] = ContextSpecificCacheLayer(csl_config)

        self._simulated_total_latency_ns = 0

    def get_total_simulated_latency(self) -> float:
        """Calculates total latency from all cache levels in this hierarchy instance."""
        total_latency = 0
        if self.l1: total_latency += self.l1._simulated_processing_time_ns
        if self.l2: total_latency += self.l2._simulated_processing_time_ns
        if self.l3: total_latency += self.l3._simulated_processing_time_ns
        if self.holographic_memory: total_latency += self.holographic_memory._simulated_processing_time_ns
        for csl in self.context_caches.values():
            total_latency += csl._simulated_processing_time_ns
        return total_latency

    def read_hierarchical(self, key: str) -> Optional[Any]:
        """Attempts to read data, traversing the cache hierarchy."""
        # L1 (if per-core hierarchy)
        if self.l1:
            entry = self.l1.read(key)
            if entry: return entry.data

        # L2
        entry = self.l2.read(key)
        if entry:
            if self.l1 and self.l1.config.is_inclusive: self.l1.write(key, entry.data) # Write back to L1 if inclusive
            return entry.data

        # L3
        if self.l3:
            entry = self.l3.read(key)
            if entry:
                if self.l2.config.is_inclusive: self.l2.write(key, entry.data)
                if self.l1 and self.l1.config.is_inclusive: self.l1.write(key, entry.data)
                return entry.data

        # Holographic Memory (as a fallback, like main memory)
        entry = self.holographic_memory.read(key)
        if entry:
            # Write back up the hierarchy if inclusive policies are met
            if self.l3 and self.l3.config.is_inclusive: self.l3.write(key, entry.data)
            if self.l2.config.is_inclusive: self.l2.write(key, entry.data)
            if self.l1 and self.l1.config.is_inclusive: self.l1.write(key, entry.data)
            return entry.data

        return None # Not found anywhere

    def write_hierarchical(self, key: str, data: Any, write_through_to_holographic: bool = True):
        """
        Writes data, typically starting at L1 and propagating based on policy (e.g., write-through, write-back).
        This is a simplified write-through model to L1/L2/L3 and optionally Holographic Memory.
        """
        if self.l1:
            self.l1.write(key, data)

        # Assume write-through for L2 and L3 for simplicity in this model
        self.l2.write(key, data)
        if self.l3:
            self.l3.write(key, data)

        if write_through_to_holographic: # Conceptually like writing to main memory
            self.holographic_memory.write(key, data)

    def read_csl(self, csl_name: str, key: str) -> Optional[Any]:
        if csl_name in self.context_caches:
            entry = self.context_caches[csl_name].read(key)
            return entry.data if entry else None
        return None

    def write_csl(self, csl_name: str, key: str, data: Any):
        if csl_name in self.context_caches:
            self.context_caches[csl_name].write(key, data)
        else:
            print(f"Warning: CSL '{csl_name}' not found in cache hierarchy.")

    def get_all_stats(self) -> Dict[str, Any]:
        stats = {}
        if self.l1: stats["L1"] = self.l1.get_stats()
        stats["L2"] = self.l2.get_stats()
        if self.l3: stats["L3"] = self.l3.get_stats()
        stats["HolographicMemory"] = self.holographic_memory.get_stats()
        stats["ContextCaches"] = {name: csl.get_stats() for name, csl in self.context_caches.items()}
        stats["TotalSimulatedLatency"] = self.get_total_simulated_latency()
        return stats

    def flush_all(self):
        if self.l1: self.l1.flush()
        self.l2.flush()
        if self.l3: self.l3.flush()
        self.holographic_memory.flush()
        for csl in self.context_caches.values():
            csl.flush()
        self._simulated_total_latency_ns = 0


# Example Usage (more extensive tests would be in a test file)
if __name__ == "__main__":
    from .config import AIVCPUConfig # Relative import for example

    # Create a sample config (assuming AIVCPUConfig is defined in config.py)
    # This is a bit circular for a standalone run, normally config.py would be importable.
    # For this __main__ block, let's quickly redefine a minimal AIVCPUConfig if needed
    try:
        AIVCPUConfig()
    except NameError: # If running this file directly and AIVCPUConfig not yet "globally" known
        @dataclass
        class MinimalCoreConfig:
            core_id: int
            l1_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L1", 64, 1.0))
        @dataclass
        class MinimalAIVCPUConfig:
            specialized_core_configs: List[MinimalCoreConfig] = field(default_factory=list)
            l2_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L2", 256, 5.0))
            l3_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L3", 1024, 20.0))
            holographic_memory_config: CacheConfig = field(default_factory=lambda: CacheConfig("HM", 8192, 100.0))
            context_specific_cache_layers_config: List[CacheConfig] = field(default_factory=list)

            def __post_init__(self): # Ensure specialized_core_configs has at least one for L1 test
                 if not self.specialized_core_configs:
                    self.specialized_core_configs.append(MinimalCoreConfig(core_id=0))
                 if not self.context_specific_cache_layers_config:
                    self.context_specific_cache_layers_config.append(CacheConfig("CSL_Test", 128, 2.0))


        test_config = MinimalAIVCPUConfig()
    else:
        test_config = AIVCPUConfig()


    # Test CacheHierarchy
    hierarchy = CacheHierarchy(config=test_config, core_id=0) # Assuming core 0 exists in config

    print("--- Initial Cache Hierarchy Stats ---")
    print(hierarchy.get_all_stats()["L1"])
    print(hierarchy.get_all_stats()["L2"])
    print(hierarchy.get_all_stats()["HolographicMemory"])
    print(hierarchy.get_all_stats()["ContextCaches"]["CSL_Test" if "CSL_Test" in hierarchy.context_caches else test_config.context_specific_cache_layers_config[0].name])


    print("\n--- Cache Operations ---")
    # Write data
    hierarchy.write_hierarchical("my_data_key_1", {"value": "Hello Doppelganger!"})
    hierarchy.write_hierarchical("my_data_key_2", {"value": "Another data point."})
    hierarchy.write_csl(test_config.context_specific_cache_layers_config[0].name, "convo_state", {"turn": 5, "sentiment": "positive"})

    # Read data - Key 1
    print("\nReading 'my_data_key_1':")
    data1 = hierarchy.read_hierarchical("my_data_key_1")
    print(f"  Retrieved: {data1}")
    self.assertTrue(data1 is not None, "Data1 should be found") # Assuming this is run via a test runner for self.assertTrue

    # Read data - Key 2 (should also be a hit in L1/L2/L3 after write)
    print("\nReading 'my_data_key_2':")
    data2 = hierarchy.read_hierarchical("my_data_key_2")
    print(f"  Retrieved: {data2}")
    self.assertTrue(data2 is not None, "Data2 should be found")


    # Read non-existent key
    print("\nReading 'non_existent_key':")
    non_existent_data = hierarchy.read_hierarchical("non_existent_key")
    print(f"  Retrieved: {non_existent_data}")
    self.assertTrue(non_existent_data is None, "Non-existent data should be None")


    # Read from CSL
    print("\nReading from CSL:")
    csl_data = hierarchy.read_csl(test_config.context_specific_cache_layers_config[0].name, "convo_state")
    print(f"  Retrieved CSL data: {csl_data}")
    self.assertTrue(csl_data is not None and csl_data["turn"] == 5, "CSL data not as expected")


    print("\n--- Stats After Operations ---")
    all_stats = hierarchy.get_all_stats()
    if "L1" in all_stats: print(f"L1 Stats: Hits={all_stats['L1']['hits']}, Misses={all_stats['L1']['misses']}")
    print(f"L2 Stats: Hits={all_stats['L2']['hits']}, Misses={all_stats['L2']['misses']}")
    if "L3" in all_stats and all_stats["L3"]: print(f"L3 Stats: Hits={all_stats['L3']['hits']}, Misses={all_stats['L3']['misses']}")
    print(f"HM Stats: Hits={all_stats['HolographicMemory']['hits']}, Misses={all_stats['HolographicMemory']['misses']}")

    csl_name_to_check = test_config.context_specific_cache_layers_config[0].name
    print(f"{csl_name_to_check} Stats: Hits={all_stats['ContextCaches'][csl_name_to_check]['hits']}, Misses={all_stats['ContextCaches'][csl_name_to_check]['misses']}")
    print(f"Total Simulated Latency: {all_stats['TotalSimulatedLatency']} ns")

    # Example of L1 miss, L2 hit scenario:
    print("\n--- L1 Miss, L2 Hit Scenario ---")
    hierarchy.l1.flush() # Flush L1 to ensure key_1 is not there
    print("L1 flushed.")
    data1_re_read = hierarchy.read_hierarchical("my_data_key_1") # Should be L1 miss, L2 hit
    print(f"Re-read 'my_data_key_1': {data1_re_read}")
    all_stats_after_reread = hierarchy.get_all_stats()
    if "L1" in all_stats_after_reread:
        print(f"L1 Stats after re-read: Hits={all_stats_after_reread['L1']['hits']}, Misses={all_stats_after_reread['L1']['misses']}")
        # L1 hits should be 0 or 1 (if written back), misses should be 1 for this specific key
        self.assertTrue(all_stats_after_reread['L1']['misses'] >= 1, "L1 should have at least one miss for my_data_key_1 after flush")
    print(f"L2 Stats after re-read: Hits={all_stats_after_reread['L2']['hits']}, Misses={all_stats_after_reread['L2']['misses']}")
    # L2 hits should have increased by 1 (or more if other reads happened)

    hierarchy.flush_all()
    print("\nAll caches flushed.")
    final_stats = hierarchy.get_all_stats()
    if "L1" in final_stats: self.assertTrue(final_stats['L1']['current_entries'] == 0 and final_stats['L1']['hits'] == 0)
    self.assertTrue(final_stats['L2']['current_entries'] == 0 and final_stats['L2']['hits'] == 0)

    print("\nCache example finished.")

# Note: The self.assertTrue calls in __main__ are for when this code might be pasted into a unittest environment.
# When run directly, they will cause an AttributeError. For direct run, print statements show behavior.
# To make it runnable directly without error, replace self.assertTrue(condition, message) with assert condition, message
if __name__ == "__main__":
    # Simplified assertions for direct run
    def assertTrue(condition, message=""): assert condition, message
    self = type('self', (object,), {'assertTrue': staticmethod(assertTrue)})() # Mock self for assertTrue

    # (The rest of the __main__ block from above, with self.assertTrue now working)
    from .config import AIVCPUConfig

    try:
        AIVCPUConfig()
    except NameError:
        @dataclass
        class MinimalCoreConfig:
            core_id: int
            l1_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L1", 64, 1.0))
        @dataclass
        class MinimalAIVCPUConfig:
            specialized_core_configs: List[MinimalCoreConfig] = field(default_factory=list)
            l2_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L2", 256, 5.0))
            l3_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L3", 1024, 20.0))
            holographic_memory_config: CacheConfig = field(default_factory=lambda: CacheConfig("HM", 8192, 100.0))
            context_specific_cache_layers_config: List[CacheConfig] = field(default_factory=list)

            def __post_init__(self):
                 if not self.specialized_core_configs:
                    self.specialized_core_configs.append(MinimalCoreConfig(core_id=0))
                 if not self.context_specific_cache_layers_config:
                    self.context_specific_cache_layers_config.append(CacheConfig("CSL_Test", 128, 2.0))
        test_config = MinimalAIVCPUConfig()
    else:
        test_config = AIVCPUConfig()

    hierarchy = CacheHierarchy(config=test_config, core_id=0)

    print("--- Initial Cache Hierarchy Stats ---") # ... (rest of the print/asserts)
    # ... (omitted for brevity, it's the same as above) ...
    hierarchy.write_hierarchical("my_data_key_1", {"value": "Hello Doppelganger!"})
    hierarchy.write_hierarchical("my_data_key_2", {"value": "Another data point."})
    csl_name_for_test = test_config.context_specific_cache_layers_config[0].name
    hierarchy.write_csl(csl_name_for_test, "convo_state", {"turn": 5, "sentiment": "positive"})

    data1 = hierarchy.read_hierarchical("my_data_key_1")
    self.assertTrue(data1 is not None, "Data1 should be found")
    data2 = hierarchy.read_hierarchical("my_data_key_2")
    self.assertTrue(data2 is not None, "Data2 should be found")
    non_existent_data = hierarchy.read_hierarchical("non_existent_key")
    self.assertTrue(non_existent_data is None, "Non-existent data should be None")
    csl_data = hierarchy.read_csl(csl_name_for_test, "convo_state")
    self.assertTrue(csl_data is not None and csl_data["turn"] == 5, "CSL data not as expected")

    if hierarchy.l1: hierarchy.l1.flush()
    data1_re_read = hierarchy.read_hierarchical("my_data_key_1")
    all_stats_after_reread = hierarchy.get_all_stats()
    if "L1" in all_stats_after_reread and hierarchy.l1: # Check if L1 exists
        self.assertTrue(all_stats_after_reread['L1']['misses'] >= 1, "L1 should have at least one miss for my_data_key_1 after flush")

    hierarchy.flush_all()
    final_stats = hierarchy.get_all_stats()
    if "L1" in final_stats and hierarchy.l1: self.assertTrue(final_stats['L1']['current_entries'] == 0 and final_stats['L1']['hits'] == 0)
    self.assertTrue(final_stats['L2']['current_entries'] == 0 and final_stats['L2']['hits'] == 0)
    print("\nCache example finished (with direct run assertions).")
