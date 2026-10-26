# Build cidr-squash from the current Git working tree.
# Set BUILDDIR outside the repository's src/ directory.
pkgname=cidr-squash
pkgver=0.1.0
pkgrel=3
pkgdesc='IPv4 CIDR optimizer with optional bounded over-coverage'
arch=('x86_64')
license=('AGPL-3.0-only')
depends=('glibc')
makedepends=('cmake')
source=()

prepare() {
    if [[ $srcdir == "$startdir/src" ]]; then
        printf '%s\n' 'Error: set BUILDDIR outside the repository src/ directory.' >&2
        return 1
    fi

    mkdir -p "$srcdir/cidr-squash"
    cp -a "$startdir/CMakeLists.txt" \
        "$startdir/CMakePresets.json" \
        "$startdir/src" \
        "$startdir/LICENSE" \
        "$startdir/README.md" \
        "$srcdir/cidr-squash/"
    if [[ -f $startdir/.clang-format ]]; then
        cp -a "$startdir/.clang-format" "$srcdir/cidr-squash/"
    fi
}

build() {
    cd "$srcdir/cidr-squash" || return 1
    cmake --preset release
    cmake --build --preset release --parallel
}

check() {
    local actual
    actual="$(
        printf '%s\n' '192.168.0.0/25' '192.168.0.128/25' |
            "$srcdir/cidr-squash/build/release/cidr-squash" -q
    )"
    [[ $actual == '192.168.0.0/24' ]]
}

package() {
    DESTDIR="$pkgdir" cmake --install "$srcdir/cidr-squash/build/release"
    install -Dm644 "$srcdir/cidr-squash/LICENSE" \
        "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 "$srcdir/cidr-squash/README.md" \
        "$pkgdir/usr/share/doc/$pkgname/README.md"
}
