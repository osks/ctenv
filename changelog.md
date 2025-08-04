# Changelog

<!-- https://keepachangelog.com/ -->

## [Unreleased]

### Fixed

- Fix handling of relative volume path. `--volume ./foo` didn't work
  as expected, the container path was not made absolute so starting
  the container failed.

### Changed

- Moved `--verbose` and `--quiet` to be global options. Now they need
  to be specified before the command (`ctenv --verbose run ...`).
  `ctenv run` now has `-v` as short for `--volume`. This means `-v`
  has different meaning before and after the command. Example: `ctenv
  -v run -v foo:/bar` means verbose and mount volume.


## v0.4

Improved config handling and removed lots of hard-coded options.


## v0.3

First release
