class Rush < Formula
  desc "Zero-dependency local CLI and stdio-only MCP quality server"
  homepage "https://github.com/jamesdsizemore/rush-cli"
  version "0.2.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-darwin-arm64.tar.gz"
    else
      url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-darwin-x86_64.tar.gz"
    end
  end

  on_linux do
    url "https://github.com/jamesdsizemore/rush-cli/releases/download/v#{version}/rush-linux-x86_64.tar.gz"
  end

  def install
    bin.install "rush"
  end

  test do
    system "#{bin}/rush", "--version"
  end
end
