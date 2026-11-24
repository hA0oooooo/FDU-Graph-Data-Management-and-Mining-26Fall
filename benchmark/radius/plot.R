# From the repository root. Interquartile ranges are timing variation within a frozen workload.
root <- "results/round2"
paths <- list.files(root, pattern = "repeats.tsv$", recursive = TRUE, full.names = TRUE)
records <- lapply(paths, function(path) {
  x <- read.delim(path, check.names = FALSE)
  a <- x[x$method == "workload", ]
  b <- x[x$method == "uniform", ]
  stopifnot(identical(a[["repeat"]], b[["repeat"]]))
  relative <- 100 * (b$mean_us - a$mean_us) / b$mean_us
  data.frame(graph = basename(dirname(path)), n = a$n[1], median = median(relative),
             lo = unname(quantile(relative, .25)), hi = unname(quantile(relative, .75)))
})
d <- do.call(rbind, records)
d <- d[order(d$median), ]
svg(file.path(root, "latency.svg"), width = 8, height = 4.8, family = "sans", bg = "white")
par(mar = c(4.3, 10, 3.3, 1.7), las = 1, xaxs = "i", fg = "#344054",
    col.axis = "#27364a", col.lab = "#27364a")
y <- seq_len(nrow(d))
xlim <- range(c(0, d$lo, d$hi))
pad <- max(diff(xlim)*.07, 2)
plot(0, type = "n", xlim = xlim + c(-pad, pad), ylim = c(.5, max(y)+.5), axes = FALSE,
     ylab = "", xlab = "Reduction in mean query latency vs tuned uniform radius (%)")
abline(v = pretty(xlim), col = "#e4e9ef", lty = "dotted")
abline(v = 0, col = "#45536a", lwd = 1.2)
axis(1); axis(2, at = y, labels = paste0(d$graph, "  (", d$n, ")"), tick = FALSE, cex.axis = .88)
segments(d$lo, y, d$hi, y, col = "#7188a6", lwd = 2.8)
points(d$median, y, pch = 21, cex = 1.15, bg = "#235a9a", col = "white")
mtext("Workload-selected radii on held-out sources", side = 3, adj = 0, line = 1.6,
      font = 2, cex = 1.15)
mtext("Paired median and middle 50% of 12 timed rounds; query counts in parentheses",
      side = 3, adj = 0, line = .4, cex = .78, col = "#475569")
invisible(dev.off())
