# AUR package

`PKGBUILD` builds Rinne from the tagged source release, runs the test suite, and installs the
desktop entry, icons and AppStream metadata. PySide6 comes from Arch's `pyside6` package. It has
been test-built with `makepkg`.

## Publishing (first time)

1. Create an account on <https://aur.archlinux.org> and add your SSH public key under
   *My Account*.
2. After the `v1.0.0` release is tagged on GitHub:

   ```sh
   git clone ssh://aur@aur.archlinux.org/rinne.git aur-rinne   # empty repo = name is free
   cp PKGBUILD aur-rinne/
   cd aur-rinne
   updpkgsums                          # replaces SKIP with the tarball's sha256 (pacman-contrib)
   makepkg -si                         # build, test and install it locally
   makepkg --printsrcinfo > .SRCINFO
   git add PKGBUILD .SRCINFO
   git commit -m "rinne 1.0.0"
   git push
   ```

## Updating for a new release

Set `pkgver` to the new version and reset `pkgrel=1`. Then run `updpkgsums`, regenerate
`.SRCINFO`, commit and push. Copy the updated `PKGBUILD` back here so the repository stays in sync.

Copies installed from the AUR don't show Rinne's in-app update button. Updates arrive through
the AUR helper (`yay -Syu`, `paru`, …).
