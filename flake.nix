{
  description = "Floppy development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Browser builds must match the playwright version in uv.lock (1.62,
    # Chromium revision 1234). Move this pin together with that version.
    nixpkgs-playwright.url = "github:NixOS/nixpkgs/6959e56fb649818335ef46fbb6c695d47587caff";
  };

  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-playwright,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
        "x86_64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      targets = {
        x86_64-linux = "x86_64-unknown-linux-musl";
        aarch64-linux = "aarch64-unknown-linux-musl";
        aarch64-darwin = "aarch64-apple-darwin";
        x86_64-darwin = "x86_64-apple-darwin";
      };

      # Exact releases instead of nixpkgs' versions:
      # - uv matches [tool.uv] required-version in pyproject.toml and the uv
      #   image the Dockerfile copies.
      # - ruff matches uv.lock. The ruff wheel ships a glibc binary that NixOS
      #   cannot run, so the shell hook points .venv/bin/ruff at this one.
      # Bump version and hashes together with those pins.
      tools = {
        uv = {
          version = "0.12.3";
          bins = [
            "uv"
            "uvx"
          ];
          hashes = {
            x86_64-linux = "sha256-BkO5+4yfsnRY5wnOb/k5aVATxBl1/3sC0/OxONjUvbM=";
            aarch64-linux = "sha256-+lE/yh6ykTM0yUT+mtvdQQJ0ocvo3QXQNpmp64UxHU4=";
            aarch64-darwin = "sha256-VG9/imxw/xOjqdK8lY2zQnKYzr8+DLdW+RdxM7cGiEM=";
            x86_64-darwin = "sha256-TJ9SJioU2jNuSkLtJJktEtDJVqzeh2GeRhHTId/6YCs=";
          };
        };
        ruff = {
          version = "0.15.8";
          bins = [ "ruff" ];
          hashes = {
            x86_64-linux = "sha256-1UG+rpnVUO1KuzodAmuQeIbHzfRKUzskYkhx49jIEzA=";
            aarch64-linux = "sha256-FeamwhaWu+WcVtDxxDdFK5YLzf6B7MO8GfqJ5qfXDrY=";
            aarch64-darwin = "sha256-lPwGH5KMjysExLOpiq0rGwTzi0yAiDm8WzOi8KY6R6M=";
            x86_64-darwin = "sha256-FT0YAQaN9gYpDoMgWM4uVgFYSsMCeIoFXQOQrfbHcs4=";
          };
        };
      };

      astralRelease =
        pkgs: name:
        let
          tool = tools.${name};
          system = pkgs.stdenv.hostPlatform.system;
        in
        pkgs.stdenvNoCC.mkDerivation {
          pname = name;
          inherit (tool) version;
          src = pkgs.fetchurl {
            url = "https://github.com/astral-sh/${name}/releases/download/${tool.version}/${name}-${targets.${system}}.tar.gz";
            hash = tool.hashes.${system};
          };
          installPhase = ''
            install -Dm755 ${pkgs.lib.concatStringsSep " " tool.bins} -t $out/bin
          '';
        };
    in
    {
      packages = forAllSystems (pkgs: {
        uv = astralRelease pkgs "uv";
        ruff = astralRelease pkgs "ruff";
      });

      devShells = forAllSystems (
        pkgs:
        let
          ruff = astralRelease pkgs "ruff";
        in
        {
          default = pkgs.mkShell {
            packages = [
              (astralRelease pkgs "uv")
              ruff
              pkgs.python312
              pkgs.redis
              # Tailwind CLI is pinned in package.json; run it with npx.
              pkgs.nodejs_22
            ];

            # Use the pinned interpreter instead of uv-managed Python downloads.
            UV_PYTHON = "${pkgs.python312}/bin/python3.12";
            UV_PYTHON_DOWNLOADS = "never";

            # Binary wheels (manylinux) expect these on a regular Linux system.
            LD_LIBRARY_PATH = pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux (
              pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc.lib
                pkgs.zlib
              ]
            );

            # The playwright wheel bundles a glibc node; use nixpkgs' node and
            # browsers instead (Linux only, where nixpkgs builds them).
            PLAYWRIGHT_NODEJS_PATH = "${pkgs.nodejs_22}/bin/node";
            PLAYWRIGHT_BROWSERS_PATH = pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux "${
              nixpkgs-playwright.legacyPackages.${pkgs.stdenv.hostPlatform.system}.playwright-driver.browsers
            }";
            PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";

            # uv sync reinstalls the wheel's ruff; re-point it on every entry.
            shellHook = pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
              if [ -e .venv/bin/ruff ] && [ ! -L .venv/bin/ruff ]; then
                ln -sf ${ruff}/bin/ruff .venv/bin/ruff
              fi
            '';
          };
        }
      );
    };
}
