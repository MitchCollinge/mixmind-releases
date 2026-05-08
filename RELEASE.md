# Building & Releasing MixMind

## Build the .app locally (no GitHub needed)

```bash
cd ~/Downloads/mixmind
npm install
npm run build:mac
```

Your `.app` will appear in `dist/mac-arm64/MixMind.app`. Drag it to `/Applications`.

---

## Set up auto-updates via GitHub (one-time)

### 1. Create a GitHub repo
Go to https://github.com/new, name it `mixmind-releases`, set to **Public**.

### 2. Update package.json
Change `YOUR_GITHUB_USERNAME` to your actual GitHub username.

### 3. Push the code
```bash
cd ~/Downloads/mixmind
git init
git add .
git commit -m "v1.1.0"
git remote add origin https://github.com/YOUR_USERNAME/mixmind-releases.git
git push -u origin main
```

### 4. Publish a release
```bash
GH_TOKEN=your_github_token npm run publish:mac
```

Get a token at: https://github.com/settings/tokens (needs `repo` scope)

Every existing MixMind install will auto-update within 5 seconds of next launch.

---

## Bump version for a new release
1. Edit `"version"` in `package.json`
2. Run `npm run publish:mac`
That's it.
