# Vendored VulkanMemoryAllocator: header-only, no upstream CMake package so the
# same target names as find_package(VulkanMemoryAllocator) are provided here.
add_library(VulkanMemoryAllocator INTERFACE)
add_library(GPUOpen::VulkanMemoryAllocator ALIAS VulkanMemoryAllocator)
target_include_directories(VulkanMemoryAllocator INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(VulkanMemoryAllocator INTERFACE Vulkan::Headers)
