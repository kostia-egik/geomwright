# Curve Trimming Contract

Status: current Layer 2 contract used by managed parametric workflows.

When a curve must be trimmed from both ends, trim it sequentially.

Correct order:

1. Trim the original curve from the first side.
2. Use that trimmed result as the source curve for the second trim.
3. Put the twice-trimmed result into the final contour.

Do not create two independent trims from the same original curve and then put
only one of them into the contour. That leaves one side untrimmed and can make
the contour miss expected path pieces.

This matters for torsion spring transition ends and any other path assembled as:

```text
trimmed segment -> connect curve -> trimmed shared segment -> connect curve -> trimmed segment
```

The shared segment must be chained through both trim operations.
