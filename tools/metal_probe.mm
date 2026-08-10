// Does runtime MSL compilation work with Command Line Tools only (no Xcode)?
// Also sanity-checks exact int32 multiply-accumulate, which is what Backend A needs.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <cstdio>

static const char *kSrc = R"MSL(
#include <metal_stdlib>
using namespace metal;

// int8 x int8 -> int32 accumulate, the core of Backend A.
kernel void dot_i8(device const char*  a   [[buffer(0)]],
                   device const char*  b   [[buffer(1)]],
                   device int*         out [[buffer(2)]],
                   constant uint&      k   [[buffer(3)]],
                   uint gid [[thread_position_in_grid]])
{
    int acc = 0;
    for (uint i = 0; i < k; ++i) {
        acc += int(a[gid * k + i]) * int(b[gid * k + i]);
    }
    out[gid] = acc;
}
)MSL";

int main() {
    @autoreleasepool {
        // MTLCreateSystemDefaultDevice() returns nil for a plain CLI binary on this
        // machine; MTLCopyAllDevices() works. Use the latter.
        id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
        if (!dev) { NSArray<id<MTLDevice>> *all = MTLCopyAllDevices();
                    if ([all count]) dev = all[0]; }
        if (!dev) { printf("FAIL: no Metal device\n"); return 1; }
        printf("device      : %s\n", [[dev name] UTF8String]);
        printf("unified mem : %s\n", [dev hasUnifiedMemory] ? "yes" : "no");
        printf("max tg mem  : %lu bytes\n", (unsigned long)[dev maxThreadgroupMemoryLength]);
        if (@available(macOS 13.0, *))
            printf("Metal3      : %s\n", [dev supportsFamily:MTLGPUFamilyMetal3] ? "yes" : "no");
        printf("Apple7      : %s\n", [dev supportsFamily:MTLGPUFamilyApple7] ? "yes" : "no");
        printf("Apple8      : %s\n", [dev supportsFamily:MTLGPUFamilyApple8] ? "yes" : "no");

        NSError *err = nil;
        MTLCompileOptions *opt = [MTLCompileOptions new];
        id<MTLLibrary> lib = [dev newLibraryWithSource:[NSString stringWithUTF8String:kSrc]
                                               options:opt error:&err];
        if (!lib) { printf("FAIL: runtime compile: %s\n", [[err localizedDescription] UTF8String]); return 1; }
        printf("runtime MSL compile: OK   <-- no Xcode needed\n");

        id<MTLFunction> fn = [lib newFunctionWithName:@"dot_i8"];
        id<MTLComputePipelineState> pso = [dev newComputePipelineStateWithFunction:fn error:&err];
        if (!pso) { printf("FAIL: pipeline: %s\n", [[err localizedDescription] UTF8String]); return 1; }
        printf("max threads/tg      : %lu\n", (unsigned long)[pso maxTotalThreadsPerThreadgroup]);

        // 256 rows of K=4096, all operands at the int8 extreme -127 * -127.
        // Worst case per row: 127*127*4096 = 66,064,384 -- overflows fp32's exact
        // integer range (2^24) but sits comfortably inside int32. This is exactly
        // the magnitude fp32 cannot represent exactly.
        const uint32_t K = 4096, ROWS = 256;
        id<MTLBuffer> ba = [dev newBufferWithLength:ROWS*K options:MTLResourceStorageModeShared];
        id<MTLBuffer> bb = [dev newBufferWithLength:ROWS*K options:MTLResourceStorageModeShared];
        id<MTLBuffer> bo = [dev newBufferWithLength:ROWS*sizeof(int32_t) options:MTLResourceStorageModeShared];
        int8_t *pa = (int8_t*)[ba contents], *pb = (int8_t*)[bb contents];
        for (uint32_t i = 0; i < ROWS*K; ++i) { pa[i] = -127; pb[i] = -127; }

        id<MTLCommandQueue> q = [dev newCommandQueue];
        id<MTLCommandBuffer> cb = [q commandBuffer];
        id<MTLComputeCommandEncoder> enc = [cb computeCommandEncoder];
        [enc setComputePipelineState:pso];
        [enc setBuffer:ba offset:0 atIndex:0];
        [enc setBuffer:bb offset:0 atIndex:1];
        [enc setBuffer:bo offset:0 atIndex:2];
        [enc setBytes:&K length:sizeof(K) atIndex:3];
        [enc dispatchThreads:MTLSizeMake(ROWS,1,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];
        [enc endEncoding];
        [cb commit];
        [cb waitUntilCompleted];
        if ([cb error]) { printf("FAIL: dispatch: %s\n", [[[cb error] localizedDescription] UTF8String]); return 1; }

        const int32_t expect = 127*127*(int32_t)K;   // 66,064,384
        int32_t *po = (int32_t*)[bo contents];
        uint32_t bad = 0;
        for (uint32_t r = 0; r < ROWS; ++r) if (po[r] != expect) ++bad;
        printf("int32 MAC exact     : %s (got %d, expected %d, %u/%u rows wrong)\n",
               bad ? "FAIL" : "OK", po[0], expect, bad, ROWS);
        return bad ? 1 : 0;
    }
}
