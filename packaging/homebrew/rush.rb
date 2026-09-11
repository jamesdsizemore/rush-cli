class Rush < Formula
  desc "Zero-dependency local CLI and stdio-only MCP quality server"
  homepage "https://github.com/jamesdsizemore/rush-cli"
  version "0.3.0"

  # sha256 checksums intentionally omitted: no real per-platform release archives have
  # been published yet. The release pipeline (P65-10) populates `sha256 "..."` per
  # `url` block once actual GitHub release assets exist.

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-darwin-arm64.tar.gz"
    else
      url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-darwin-x86_64.tar.gz"
    end
  end

  on_linux do
    if Hardware::CPU.arm?
      url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-linux-arm64.tar.gz"
    else
      url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-linux-x86_64.tar.gz"
    end
  end

  def install
    bin.install "rush"
  end

  test do
    system "#{bin}/rush", "--version"
  end
end
