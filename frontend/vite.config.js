import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import adapter from '@sveltejs/adapter-static';

const outDir = process.env.BUILD_OUT_DIR || '../artifacts/site';

export default defineConfig({
	plugins: [
		sveltekit({
			adapter: adapter({
				pages: outDir,
				assets: outDir,
				fallback: '200.html',
				precompress: false,
				strict: false
			}),
			paths: {
				relative: true
			}
		})
	]
});
