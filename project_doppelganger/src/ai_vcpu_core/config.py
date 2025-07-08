from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any

class CoreType(Enum):
    GENERAL_PURPOSE = "GeneralPurpose"
    LANGUAGE_MODELER = "Language_Modeler" # Specialized for NLP tasks
    VISION_INTERPRETER = "Vision_Interpreter" # Specialized for image/video analysis
    FUSION_CORE = "Fusion_Core" # For multi-modal data integration
    MEMORY_CORE = "Memory_Core" # Specialized for complex memory operations
    # Add other specialized core types as needed

class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4 # For system-level or urgent tasks

@dataclass
class CacheConfig:
    name: str
    size_kb: int
    latency_ns: float # Access latency in nanoseconds
    associativity: int = 8 # e.g., 8-way set associative
    is_inclusive: bool = True # Whether this cache is inclusive of lower levels

@dataclass
class CoreConfig:
    core_id: int
    core_type: CoreType
    clock_speed_ghz: float = 3.0
    supported_instructions: List[str] = field(default_factory=list) # e.g., ["text_analysis", "sentiment_extraction"]
    # Conceptual: performance multipliers for certain task types
    performance_factors: Dict[str, float] = field(default_factory=dict)
    l1_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L1", 64, 1.0))

@dataclass
class AIVCPUConfig:
    num_general_cores: int = 2
    specialized_core_configs: List[CoreConfig] = field(default_factory=list)

    l2_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L2", 256, 5.0))
    l3_cache_config: CacheConfig = field(default_factory=lambda: CacheConfig("L3", 8192, 20.0, is_inclusive=False)) # L3 often non-inclusive victim cache

    holographic_memory_config: CacheConfig = field(default_factory=lambda: CacheConfig("HolographicMemory", 1024*1024, 100.0)) # 1GB, conceptual
    context_specific_cache_layers_config: List[CacheConfig] = field(default_factory=list)

    # Default configuration for specialized cores if none are provided
    default_language_modeler_cores: int = 1
    default_vision_interpreter_cores: int = 0 # Set to 0 as it's conceptual for Doppelganger
    default_fusion_cores: int = 1
    default_memory_cores: int = 1

    # Simulation parameters
    task_scheduling_overhead_ms: float = 0.01 # Overhead for scheduling a task
    cache_miss_penalty_multiplier: float = 1.5 # Multiplier for latency on cache miss to next level

    def __post_init__(self):
        # If no specialized_core_configs are provided, create some defaults
        if not self.specialized_core_configs:
            core_id_counter = self.num_general_cores # Start IDs after general cores

            for _ in range(self.default_language_modeler_cores):
                self.specialized_core_configs.append(
                    CoreConfig(core_id=core_id_counter, core_type=CoreType.LANGUAGE_MODELER,
                               supported_instructions=["analyze_text", "extract_entities", "summarize"])
                )
                core_id_counter += 1

            for _ in range(self.default_vision_interpreter_cores):
                 self.specialized_core_configs.append(
                    CoreConfig(core_id=core_id_counter, core_type=CoreType.VISION_INTERPRETER,
                               supported_instructions=["analyze_image_features", "detect_objects"]) # Conceptual
                )
                 core_id_counter += 1

            for _ in range(self.default_fusion_cores):
                self.specialized_core_configs.append(
                    CoreConfig(core_id=core_id_counter, core_type=CoreType.FUSION_CORE,
                               supported_instructions=["fuse_multi_modal_data", "generate_cross_modal_embeddings"])
                )
                core_id_counter += 1

            for _ in range(self.default_memory_cores):
                self.specialized_core_configs.append(
                    CoreConfig(core_id=core_id_counter, core_type=CoreType.MEMORY_CORE,
                               supported_instructions=["store_long_term_memory", "retrieve_associative_memory"])
                )
                core_id_counter += 1

        # Example CSL config if not provided
        if not self.context_specific_cache_layers_config:
            self.context_specific_cache_layers_config.append(
                CacheConfig(name="CSL_ConversationHistory", size_kb=1024, latency_ns=2.0, associativity=16)
            )
            self.context_specific_cache_layers_config.append(
                CacheConfig(name="CSL_PersonaState", size_kb=512, latency_ns=1.5, associativity=8)
            )


# Example Usage:
if __name__ == "__main__":
    config = AIVCPUConfig(num_general_cores=4)
    print("Default AIVCPU Config:")
    print(f"  General Cores: {config.num_general_cores}")
    print(f"  L2 Cache: {config.l2_cache_config.name} Size: {config.l2_cache_config.size_kb}KB")
    print(f"  L3 Cache: {config.l3_cache_config.name} Size: {config.l3_cache_config.size_kb}KB")
    print(f"  Holographic Memory: {config.holographic_memory_config.name} Size: {config.holographic_memory_config.size_kb}KB")

    print("\n  Specialized Cores by default:")
    for core_conf in config.specialized_core_configs:
        print(f"    Core ID: {core_conf.core_id}, Type: {core_conf.core_type.value}, L1: {core_conf.l1_cache_config.size_kb}KB")
        print(f"      Supported Instructions: {core_conf.supported_instructions}")

    print("\n  Context-Specific Cache Layers by default:")
    for csl_conf in config.context_specific_cache_layers_config:
        print(f"    CSL: {csl_conf.name}, Size: {csl_conf.size_kb}KB, Latency: {csl_conf.latency_ns}ns")

    # Custom config example
    custom_special_cores = [
        CoreConfig(core_id=2, core_type=CoreType.LANGUAGE_MODELER, clock_speed_ghz=4.0,
                   l1_cache_config=CacheConfig("L1_LM", 128, 0.8)),
        CoreConfig(core_id=3, core_type=CoreType.FUSION_CORE, clock_speed_ghz=3.5)
    ]
    custom_csl = [CacheConfig("CSL_Custom", 2048, 1.0)]

    custom_config = AIVCPUConfig(
        num_general_cores=2,
        specialized_core_configs=custom_special_cores,
        l2_cache_config=CacheConfig("L2_Custom", 512, 4.0),
        context_specific_cache_layers_config=custom_csl
    )
    print("\nCustom AIVCPU Config:")
    print(f"  General Cores: {custom_config.num_general_cores}")
    print(f"  L2 Cache: {custom_config.l2_cache_config.name} Size: {custom_config.l2_cache_config.size_kb}KB")
    print("\n  Specialized Cores (custom):")
    for core_conf in custom_config.specialized_core_configs:
        print(f"    Core ID: {core_conf.core_id}, Type: {core_conf.core_type.value}, L1: {core_conf.l1_cache_config.size_kb}KB")
    print("\n  Context-Specific Cache Layers (custom):")
    for csl_conf in custom_config.context_specific_cache_layers_config:
        print(f"    CSL: {csl_conf.name}, Size: {csl_conf.size_kb}KB, Latency: {csl_conf.latency_ns}ns")
