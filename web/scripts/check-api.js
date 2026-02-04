import fetch from 'node-fetch';

const API_URL = process.env.INTERNAL_API_URL || process.env.PUBLIC_API_URL || 'http://localhost:8000/api/v1';

async function checkApi() {
    console.log(`🔍 Checking API connectivity: ${API_URL}`);

    try {
        // 1. Check Config
        const configUrl = `${API_URL}/config`;
        const configRes = await fetch(configUrl);

        if (!configRes.ok) {
            throw new Error(`❌ Config endpoint failed: ${configRes.status} ${configRes.statusText}`);
        }
        console.log('✅ Config endpoint OK');

        // 2. Check Catalog (Critical!)
        const catalogUrl = `${API_URL}/catalog?limit=1`;
        const catalogRes = await fetch(catalogUrl);

        if (!catalogRes.ok) {
            throw new Error(`❌ Catalog endpoint failed: ${catalogRes.status} ${catalogRes.statusText}`);
        }

        const catalogData = await catalogRes.json();
        const productCount = catalogData.meta?.total || 0;

        if (productCount === 0) {
            throw new Error('❌ API returned 0 products! Something is wrong (empty DB or wrong DB connection).');
        }

        console.log(`✅ Catalog endpoint OK (Found ${productCount} products)`);
        console.log('🚀 API check passed. Proceeding to build...');
        process.exit(0);

    } catch (error) {
        console.error('\n⛔️ FATAL: API Check Failed!');
        console.error(error.message);
        console.error('\nCheck your INTERNAL_API_URL or PUBLIC_API_URL environment variables.');
        process.exit(1);
    }
}

checkApi();
