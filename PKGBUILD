pkgname=ksystemstats_scripts
pkgver=1.0.0
pkgrel=1
pkgdesc='Simple way to create custom sensors for KDE System Monitor via text streams'
arch=(x86_64)
url='https://github.com/KerJoe/ksystemstats_scripts'
license=(GPL-3.0-or-later)
depends=(qt6-base
         libksysguard
         kcoreaddons
         ki18n
         ksystemstats)
makedepends=(git
             extra-cmake-modules)
source=(git+https://github.com/KerJoe/ksystemstats_scripts.git)
sha256sums=('SKIP')

build() {
  cd "$srcdir/ksystemstats_scripts"
  cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr -B build
  cmake --build build
}

package() {
  cd "$srcdir/ksystemstats_scripts"
  DESTDIR="$pkgdir" cmake --install build
}
