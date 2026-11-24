# Run after summarize.py, from the repository root.
root <- "results/round2"
confirm <- read.delim(file.path(root, "holdout-summary.tsv"), check.names = FALSE)
records <- lapply(split(confirm, confirm$graph), function(group) {
  graph <- group$graph[1]
  x <- read.delim(file.path(root, graph, "repeats.tsv"), check.names = FALSE)
  a <- x[x$method == "workload", ]
  b <- x[x$method == "uniform", ]
  stopifnot(identical(a[["repeat"]], b[["repeat"]]), nrow(group) == 3)
  initial <- median(100 * (b$mean_us - a$mean_us) / b$mean_us)
  saved <- group$paired_percent_saved_vs_uniform
  data.frame(graph, same = tolower(as.character(group$identical_radii[1])) == "true",
             n = sum(group$n), initial, mid = median(saved), lo = min(saved), hi = max(saved))
})
d <- do.call(rbind, records)
d <- d[order(d$mid), ]
svg(file.path(root, "latency.svg"), width = 8.6, height = 5.4, family = "sans", bg = "white")
par(mar = c(5.6, 10, 3.6, 2.3), las = 1, xaxs = "i", fg = "#344054",
    col.axis = "#27364a", col.lab = "#27364a")
y <- seq_len(nrow(d))
span <- range(c(0, d$initial, d$lo, d$hi))
pad <- max(diff(span)*.07, 2)
plot(0, type = "n", xlim = span + c(-pad, pad), ylim = c(.45, max(y)+.6), axes = FALSE,
     ylab = "", xlab = "Reduction in mean query latency vs tuned uniform radius (%)")
abline(v = pretty(span), col = "#e2e6eb", lty = "dotted")
abline(v = 0, col = "#47556a", lwd = 1.3)
axis(1); axis(2, at = y, labels = paste0(d$graph, ifelse(d$same,"*",""), "  (", d$n, ")"), tick = FALSE, cex.axis = .88)
segments(d$lo,y+.1,d$hi,y+.1,col = "#7893af", lwd = 2.4)
points(d$mid,y+.1,pch = 19,cex = .95,col = "#195794")
points(d$initial,y-.15,pch = 1,cex = .88,col = "#3f4a59",lwd = 1.3)
mtext("Do learned radii transfer to new sources?", side = 3, adj = 0, line = 2, font = 2, cex = 1.2)
mtext("Open circle: first test. Blue dot and range: median, minimum and maximum across three new groups.",
      side = 3, adj = 0, line = .78, cex = .75, col = "#475569")
mtext("Positive favors learned radii. * Identical radii; timing differences are noise. Parentheses: new queries.",
      side = 1, adj = 0, line = 4.35, cex = .73, col = "#475569")
invisible(dev.off())
