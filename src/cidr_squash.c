/*
 * cidrsquash.c - IPv4 CIDR optimizer with bounded over-coverage.
 *
 * Input:  IPv4 addresses or CIDRs, one per line (stdin or file).
 * Output: sorted IPv4 CIDRs on stdout.
 *
 * The program first computes the exact union and emits its minimal CIDR cover.
 * Then, with -p PERCENT, it greedily replaces groups of CIDRs by a common
 * supernet while keeping the total number of additionally covered IPv4
 * addresses <= PERCENT of the exact covered address count.
 *
 * No external libraries are required; libc only.
 *
 * Example:
 *   ./cidrsquash -p 0.01 direct.txt > direct.optimized.txt
 *
 * Build:
 *   cc -O2 -std=c99 -Wall -Wextra -Wpedantic -o cidrsquash cidrsquash.c
 */

#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NONE UINT32_MAX

typedef struct {
    uint32_t lo;
    uint32_t hi;
} Interval;

typedef struct {
    Interval *v;
    size_t n;
    size_t cap;
} IntervalVec;

typedef struct {
    uint32_t child[2];
    uint32_t parent;
    uint32_t active_count;
    uint32_t version;
    uint64_t covered;
    uint64_t cur_extra;
    uint8_t depth;
    uint8_t exact;
    uint8_t collapsed;
    uint8_t _pad;
} Node;

typedef struct {
    Node *v;
    uint32_t n;
    uint32_t cap;
} NodeVec;

typedef struct {
    uint32_t node;
    uint32_t version;
    uint32_t gain;
    uint32_t _pad;
    uint64_t extra;
} Candidate;

typedef struct {
    Candidate *v;
    size_t n;
    size_t cap;
} Heap;

static void die(const char *msg)
{
    fprintf(stderr, "cidrsquash: %s\n", msg);
    exit(1);
}

static void *xrealloc(void *p, size_t n)
{
    void *q = realloc(p, n);
    if (!q)
        die("out of memory");
    return q;
}

static void intervals_push(IntervalVec *a, uint32_t lo, uint32_t hi)
{
    if (a->n == a->cap) {
        size_t nc = a->cap ? a->cap * 2 : 4096;
        a->v = xrealloc(a->v, nc * sizeof(*a->v));
        a->cap = nc;
    }
    a->v[a->n].lo = lo;
    a->v[a->n].hi = hi;
    a->n++;
}

static int interval_cmp(const void *ap, const void *bp)
{
    const Interval *a = ap;
    const Interval *b = bp;
    if (a->lo < b->lo)
        return -1;
    if (a->lo > b->lo)
        return 1;
    if (a->hi < b->hi)
        return -1;
    if (a->hi > b->hi)
        return 1;
    return 0;
}

static int parse_ipv4(const char *s, const char **endp, uint32_t *out)
{
    uint32_t parts[4];
    int i;
    const char *p = s;

    for (i = 0; i < 4; i++) {
        unsigned long v = 0;
        int digits = 0;

        while (isdigit((unsigned char)*p)) {
            v = v * 10 + (unsigned)(*p - '0');
            if (v > 255)
                return 0;
            p++;
            digits++;
        }
        if (!digits)
            return 0;
        parts[i] = (uint32_t)v;
        if (i != 3) {
            if (*p != '.')
                return 0;
            p++;
        }
    }

    *out = (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3];
    *endp = p;
    return 1;
}

static int parse_line(char *line, uint32_t *lo, uint32_t *hi)
{
    char *p = line;
    const char *end;
    uint32_t ip;
    unsigned prefix = 32;
    uint32_t mask;

    while (isspace((unsigned char)*p))
        p++;
    if (*p == '\0' || *p == '\n' || *p == '#')
        return 0;

    if (!parse_ipv4(p, &end, &ip))
        return -1;
    p = (char *)end;

    if (*p == '/') {
        char *q;
        unsigned long x;

        errno = 0;
        x = strtoul(p + 1, &q, 10);
        if (errno || q == p + 1 || x > 32)
            return -1;
        prefix = (unsigned)x;
        p = q;
    }

    while (isspace((unsigned char)*p))
        p++;
    if (*p != '\0' && *p != '\n' && *p != '#')
        return -1;

    if (prefix == 0) {
        *lo = 0;
        *hi = UINT32_MAX;
        return 1;
    }

    mask = UINT32_MAX << (32 - prefix);
    *lo = ip & mask;
    *hi = *lo | ~mask;
    return 1;
}

static size_t merge_intervals(Interval *v, size_t n)
{
    size_t i, out;

    if (n == 0)
        return 0;

    qsort(v, n, sizeof(*v), interval_cmp);
    out = 0;

    for (i = 1; i < n; i++) {
        uint64_t next_allowed = (uint64_t)v[out].hi + 1ULL;
        if ((uint64_t)v[i].lo <= next_allowed) {
            if (v[i].hi > v[out].hi)
                v[out].hi = v[i].hi;
        } else {
            out++;
            v[out] = v[i];
        }
    }
    return out + 1;
}

static void nodes_reserve(NodeVec *t, uint32_t need)
{
    if (need <= t->cap)
        return;
    uint32_t nc = t->cap ? t->cap : 4096;
    while (nc < need) {
        if (nc > UINT32_MAX / 2)
            die("too many trie nodes");
        nc *= 2;
    }
    t->v = xrealloc(t->v, (size_t)nc * sizeof(*t->v));
    t->cap = nc;
}

static uint32_t node_new(NodeVec *t, uint32_t parent, uint8_t depth)
{
    Node *n;
    uint32_t idx;

    nodes_reserve(t, t->n + 1);
    idx = t->n++;
    n = &t->v[idx];
    memset(n, 0, sizeof(*n));
    n->child[0] = NONE;
    n->child[1] = NONE;
    n->parent = parent;
    n->depth = depth;
    return idx;
}

static void trie_insert(NodeVec *t, uint32_t base, unsigned prefix)
{
    uint32_t idx = 0;
    unsigned d;

    if (t->v[idx].exact)
        return;

    for (d = 0; d < prefix; d++) {
        unsigned bit;
        uint32_t next;

        if (t->v[idx].exact)
            return;

        bit = (base >> (31 - d)) & 1U;
        next = t->v[idx].child[bit];
        if (next == NONE) {
            next = node_new(t, idx, (uint8_t)(d + 1));
            t->v[idx].child[bit] = next;
        }
        idx = next;
    }

    t->v[idx].exact = 1;
}

static unsigned ctz32_or_32(uint32_t x)
{
    if (x == 0)
        return 32;
#if defined(__GNUC__) || defined(__clang__)
    return (unsigned)__builtin_ctz(x);
#else
    {
        unsigned n = 0;
        while ((x & 1U) == 0) {
            x >>= 1;
            n++;
        }
        return n;
    }
#endif
}

static uint32_t add_exact_range_as_cidrs(NodeVec *t, uint32_t lo, uint32_t hi)
{
    uint64_t cur = lo;
    uint64_t end = hi;
    uint32_t count = 0;

    while (cur <= end) {
        uint32_t cur32 = (uint32_t)cur;
        unsigned host_bits = ctz32_or_32(cur32);
        uint64_t block = 1ULL << host_bits;
        uint64_t remaining = end - cur + 1ULL;
        unsigned prefix;

        while (block > remaining) {
            block >>= 1;
            host_bits--;
        }
        prefix = 32 - host_bits;
        trie_insert(t, cur32, prefix);
        count++;
        cur += block;
    }

    return count;
}

static uint64_t prefix_size(unsigned depth)
{
    return 1ULL << (32 - depth);
}

static void compute_stats(NodeVec *t, uint32_t idx)
{
    Node *n = &t->v[idx];
    uint64_t covered = 0;
    uint32_t active = 0;
    int b;

    if (n->exact) {
        n->covered = prefix_size(n->depth);
        n->active_count = 1;
        n->cur_extra = 0;
        return;
    }

    for (b = 0; b < 2; b++) {
        uint32_t c = n->child[b];
        if (c == NONE)
            continue;
        compute_stats(t, c);
        covered += t->v[c].covered;
        active += t->v[c].active_count;
    }

    n->covered = covered;
    n->active_count = active;
    n->cur_extra = 0;
}

static int candidate_less(const Candidate *a, const Candidate *b)
{
    long double ra, rb;

    if (a->extra == 0 && b->extra != 0)
        return 1;
    if (b->extra == 0 && a->extra != 0)
        return 0;

    ra = (long double)a->extra / (long double)a->gain;
    rb = (long double)b->extra / (long double)b->gain;
    if (ra < rb)
        return 1;
    if (ra > rb)
        return 0;
    if (a->extra < b->extra)
        return 1;
    if (a->extra > b->extra)
        return 0;
    if (a->gain > b->gain)
        return 1;
    if (a->gain < b->gain)
        return 0;
    return a->node < b->node;
}

static void heap_push(Heap *h, Candidate c)
{
    size_t i;

    if (h->n == h->cap) {
        size_t nc = h->cap ? h->cap * 2 : 4096;
        h->v = xrealloc(h->v, nc * sizeof(*h->v));
        h->cap = nc;
    }

    i = h->n++;
    h->v[i] = c;
    while (i > 0) {
        size_t p = (i - 1) / 2;
        Candidate tmp;
        if (!candidate_less(&h->v[i], &h->v[p]))
            break;
        tmp = h->v[i];
        h->v[i] = h->v[p];
        h->v[p] = tmp;
        i = p;
    }
}

static int heap_pop(Heap *h, Candidate *out)
{
    size_t i;

    if (h->n == 0)
        return 0;

    *out = h->v[0];
    h->n--;
    if (h->n == 0)
        return 1;

    h->v[0] = h->v[h->n];
    i = 0;

    for (;;) {
        size_t l = i * 2 + 1;
        size_t r = l + 1;
        size_t best = i;
        Candidate tmp;

        if (l < h->n && candidate_less(&h->v[l], &h->v[best]))
            best = l;
        if (r < h->n && candidate_less(&h->v[r], &h->v[best]))
            best = r;
        if (best == i)
            break;

        tmp = h->v[i];
        h->v[i] = h->v[best];
        h->v[best] = tmp;
        i = best;
    }

    return 1;
}

static int is_branch_candidate(const NodeVec *t, uint32_t idx)
{
    const Node *n = &t->v[idx];
    uint32_t a, b;

    if (n->exact || n->collapsed || n->active_count <= 1)
        return 0;

    a = n->child[0];
    b = n->child[1];
    if (a == NONE || b == NONE)
        return 0;
    if (t->v[a].active_count == 0 || t->v[b].active_count == 0)
        return 0;
    return 1;
}

static Candidate make_candidate(const NodeVec *t, uint32_t idx)
{
    const Node *n = &t->v[idx];
    Candidate c;
    uint64_t total_extra = prefix_size(n->depth) - n->covered;

    c.node = idx;
    c.version = n->version;
    c.gain = n->active_count - 1;
    c._pad = 0;
    c.extra = total_extra - n->cur_extra;
    return c;
}

static int has_collapsed_ancestor(const NodeVec *t, uint32_t idx)
{
    uint32_t p = t->v[idx].parent;
    while (p != NONE) {
        if (t->v[p].collapsed)
            return 1;
        p = t->v[p].parent;
    }
    return 0;
}

static void push_if_candidate(const NodeVec *t, Heap *h, uint32_t idx)
{
    if (is_branch_candidate(t, idx))
        heap_push(h, make_candidate(t, idx));
}

static void merge_node(NodeVec *t, Heap *h, uint32_t idx)
{
    Node *n = &t->v[idx];
    uint32_t reduction = n->active_count - 1;
    uint64_t total_extra = prefix_size(n->depth) - n->covered;
    uint64_t inc_extra = total_extra - n->cur_extra;
    uint32_t p;

    n->collapsed = 1;
    n->active_count = 1;
    n->cur_extra = total_extra;
    n->version++;

    p = n->parent;
    while (p != NONE) {
        Node *a = &t->v[p];
        a->active_count -= reduction;
        a->cur_extra += inc_extra;
        a->version++;
        push_if_candidate(t, h, p);
        p = a->parent;
    }
}

static void print_ipv4(uint32_t ip)
{
    printf("%u.%u.%u.%u", (ip >> 24) & 255U, (ip >> 16) & 255U, (ip >> 8) & 255U, ip & 255U);
}

static void output_trie(const NodeVec *t, uint32_t idx, uint32_t base)
{
    const Node *n = &t->v[idx];
    int b;

    if (n->active_count == 0)
        return;

    if (n->exact || n->collapsed) {
        print_ipv4(base);
        printf("/%u\n", (unsigned)n->depth);
        return;
    }

    for (b = 0; b < 2; b++) {
        uint32_t c = n->child[b];
        uint32_t child_base = base;
        if (c == NONE || t->v[c].active_count == 0)
            continue;
        if (b && n->depth < 32)
            child_base |= 1U << (31 - n->depth);
        output_trie(t, c, child_base);
    }
}

static void usage(FILE *f, const char *argv0)
{
    fprintf(f,
            "Usage: %s [-p PERCENT] [-q] [FILE|-]\n"
            "\n"
            "IPv4-only CIDR squasher with bounded over-coverage.\n"
            "Input lines: A.B.C.D or A.B.C.D/PREFIX.\n"
            "Output: sorted CIDRs on stdout.\n"
            "\n"
            "  -p PERCENT  max additional coverage as %% of exact coverage\n"
            "              (default: 0; example: 0.01 means 0.01%%)\n"
            "  -q          suppress statistics on stderr\n"
            "  -h          show this help\n",
            argv0);
}

int main(int argc, char **argv)
{
    const char *path = NULL;
    FILE *in = stdin;
    IntervalVec iv = { 0 };
    NodeVec tree = { 0 };
    Heap heap = { 0 };
    char line[256];
    unsigned long line_no = 0;
    uint64_t input_entries = 0;
    uint64_t exact_cidrs = 0;
    long double percent = 0.0L;
    uint64_t budget, used;
    int quiet = 0;
    int i;

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-p") == 0) {
            char *end;
            if (++i >= argc)
                die("-p requires a value");
            errno = 0;
            percent = strtold(argv[i], &end);
            if (errno || *end != '\0' || percent < 0.0L)
                die("invalid -p percentage");
        } else if (strcmp(argv[i], "-q") == 0) {
            quiet = 1;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            usage(stdout, argv[0]);
            return 0;
        } else if (strcmp(argv[i], "-") == 0) {
            if (path)
                die("only one input file is allowed");
            path = "-";
        } else if (argv[i][0] == '-') {
            usage(stderr, argv[0]);
            return 2;
        } else {
            if (path)
                die("only one input file is allowed");
            path = argv[i];
        }
    }

    if (path && strcmp(path, "-") != 0) {
        in = fopen(path, "r");
        if (!in) {
            fprintf(stderr, "cidrsquash: cannot open %s: %s\n", path, strerror(errno));
            return 1;
        }
    }

    while (fgets(line, sizeof(line), in)) {
        uint32_t lo, hi;
        int r;

        line_no++;
        if (!strchr(line, '\n') && !feof(in)) {
            fprintf(stderr, "cidrsquash: line %lu too long\n", line_no);
            return 1;
        }

        r = parse_line(line, &lo, &hi);
        if (r < 0) {
            fprintf(stderr, "cidrsquash: invalid input at line %lu: %s", line_no, line);
            if (!strchr(line, '\n'))
                fputc('\n', stderr);
            return 1;
        }
        if (r == 0)
            continue;

        intervals_push(&iv, lo, hi);
        input_entries++;
    }

    if (ferror(in))
        die("read error");
    if (in != stdin)
        fclose(in);

    if (iv.n == 0) {
        if (!quiet)
            fprintf(stderr, "cidrsquash: no IPv4 entries\n");
        free(iv.v);
        return 0;
    }

    iv.n = merge_intervals(iv.v, iv.n);

    node_new(&tree, NONE, 0); /* root */

    for (size_t k = 0; k < iv.n; k++)
        exact_cidrs += add_exact_range_as_cidrs(&tree, iv.v[k].lo, iv.v[k].hi);

    compute_stats(&tree, 0);

    if (tree.v[0].covered == 0)
        die("internal error: empty trie");

    budget = (uint64_t)((long double)tree.v[0].covered * percent / 100.0L);

    for (uint32_t idx = 0; idx < tree.n; idx++)
        push_if_candidate(&tree, &heap, idx);

    used = 0;
    for (;;) {
        Candidate c;
        Node *n;
        Candidate now;

        if (!heap_pop(&heap, &c))
            break;

        n = &tree.v[c.node];
        if (c.version != n->version)
            continue;
        if (!is_branch_candidate(&tree, c.node))
            continue;
        if (has_collapsed_ancestor(&tree, c.node))
            continue;

        now = make_candidate(&tree, c.node);
        if (now.version != c.version || now.gain != c.gain || now.extra != c.extra)
            continue;

        if (now.extra > budget - used)
            continue;

        merge_node(&tree, &heap, c.node);
        used = tree.v[0].cur_extra;
    }

    output_trie(&tree, 0, 0);

    if (!quiet) {
        long double actual =
            100.0L * (long double)tree.v[0].cur_extra / (long double)tree.v[0].covered;
        fprintf(stderr, "input entries:      %" PRIu64 "\n", input_entries);
        fprintf(stderr, "merged intervals:   %zu\n", iv.n);
        fprintf(stderr, "exact CIDRs:        %" PRIu64 "\n", exact_cidrs);
        fprintf(stderr, "output CIDRs:       %u\n", tree.v[0].active_count);
        fprintf(stderr, "exact IPv4 covered: %" PRIu64 "\n", tree.v[0].covered);
        fprintf(stderr, "extra IPv4 covered: %" PRIu64 "\n", tree.v[0].cur_extra);
        fprintf(stderr, "over-coverage:      %.8Lf%%\n", actual);
        fprintf(stderr, "budget:             %" PRIu64 " IPv4 (%.8Lf%%)\n", budget, percent);
        fprintf(stderr, "trie nodes:         %u\n", tree.n);
    }

    free(heap.v);
    free(tree.v);
    free(iv.v);
    return 0;
}
