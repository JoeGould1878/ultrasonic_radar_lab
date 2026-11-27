/**
 * @file test_util.h
 * @brief Tiny assert helpers for the laptop tests (no framework needed).
 */
#pragma once

#include <math.h>
#include <stdio.h>

static int test_failures = 0;
static int test_checks = 0;   /* reported by TEST_RESULT */

#define CHECK(cond) do { \
    test_checks++; \
    if (!(cond)) { printf("  FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); test_failures++; } \
} while (0)

#define CHECK_NEAR(a, b, tol) do { \
    double _a = (a), _b = (b); \
    test_checks++; \
    if (fabs(_a - _b) > (tol)) { \
        printf("  FAIL %s:%d  %s = %g, expected %g +/- %g\n", __FILE__, __LINE__, #a, _a, _b, (double)(tol)); \
        test_failures++; } \
} while (0)

#define TEST_RESULT() (test_failures == 0 \
    ? (printf("  ok (%d checks)\n", test_checks), 0) \
    : (printf("  %d of %d checks FAILED\n", test_failures, test_checks), 1))
