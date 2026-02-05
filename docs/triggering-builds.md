# Triggering Automated Builds

The project includes a GitHub Actions workflow that automatically builds and publishes the Docker image to GitHub Container Registry (GHCR).

There are two primary ways to trigger this workflow:

## 1. Push to `main` (Latest)
Any commit pushed (or merged) to the `main` branch will trigger a build. The resulting image will be tagged as `latest`.

```bash
git add .
git commit -m "Update configuration logic"
git push origin main
```
**Result**: `ghcr.io/username/repo:main` (and usually treated as latest)

## 2. Release Tags (Versioning)
To create a strictly versioned release (e.g., `v1.0.0`), push a git tag. This is recommended for stability.

```bash
# Create a tag
git tag v1.0.0

# Push the tag
git push origin v1.0.0
```

**Result**: `ghcr.io/username/repo:v1.0.0`

## Monitoring the Build
1.  Go to your GitHub Repository.
2.  Click on the **Actions** tab.
3.  Click on the **Docker** workflow.
4.  You can see the live logs of the build and push process.

## Where is my Image?
Once the Action completes successfully, the image will appear in the **Packages** section on the main page of your repository (right sidebar).
