import { Readable } from 'node:stream'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { beforeAll, describe, expect, it } from 'vitest'
import { createRequestListener } from '../server'
import { MintService } from '../service'
import { loadConfigFromEnv } from '../config'
import { generateMintKeypair, importSigningKey } from '../keys'

type TestResponse = {
    status: number
    headers: Map<string, string>
    text: () => Promise<string>
    json: () => Promise<unknown>
}

let request: (method: string, path: string, body?: unknown) => Promise<TestResponse>
let publicJwk: JsonWebKey

beforeAll(async () => {
    const keypair = await generateMintKeypair()
    publicJwk = keypair.publicJwk
    const config = loadConfigFromEnv({ MINT_PRIVATE_JWK: JSON.stringify(keypair.privateJwk) }) // no address -> unconfigured
    const service = new MintService({ config, signingKey: await importSigningKey(keypair.privateJwk) })
    const listener = createRequestListener({ service, publicJwk: keypair.publicJwk })

    request = async (method: string, path: string, body?: unknown): Promise<TestResponse> => {
        const chunks = body === undefined ? [] : [Buffer.from(JSON.stringify(body))]
        const req = Readable.from(chunks) as IncomingMessage
        req.method = method
        req.url = path

        return await new Promise<TestResponse>((resolve, reject) => {
            const headers = new Map<string, string>()
            const parts: Buffer[] = []
            let status = 200
            const res = {
                get statusCode() {
                    return status
                },
                set statusCode(next: number) {
                    status = next
                },
                setHeader(name: string, value: number | string | readonly string[]) {
                    headers.set(name.toLowerCase(), Array.isArray(value) ? value.join(',') : String(value))
                    return res as ServerResponse
                },
                end(chunk?: string | Uint8Array) {
                    if (chunk !== undefined) {
                        parts.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
                    }
                    const payload = Buffer.concat(parts).toString('utf8')
                    resolve({
                        status,
                        headers,
                        text: async () => payload,
                        json: async () => JSON.parse(payload) as unknown,
                    })
                    return res as ServerResponse
                },
            } as unknown as ServerResponse

            listener(req, res).catch(reject)
        })
    }
})

describe('mint HTTP server', () => {
    it('GET /health reports liveness + configured flag + pooled demand', async () => {
        const res = await request('GET', '/health')
        expect(res.status).toBe(200)
        expect(await res.json()).toEqual({ ok: true, configured: false, waiting: 0 })
    })

    it('GET /pubkey serves the verify key for the product build', async () => {
        const res = await request('GET', '/pubkey')
        expect(res.status).toBe(200)
        const body = await res.json() as { jwk: JsonWebKey }
        expect(body.jwk.x).toBe(publicJwk.x)
        expect(body.jwk.d).toBeUndefined()
    })

    it('POST /checkout pools demand (reserves) while unconfigured', async () => {
        const res = await request('POST', '/checkout', { email: 'a@b.com' })
        expect(res.status).toBe(202)
        const body = await res.json() as { status: string }
        expect(body.status).toBe('reserved')
    })

    it('GET / serves the self-contained checkout page (no third-party checkout)', async () => {
        const res = await request('GET', '/')
        expect(res.status).toBe(200)
        expect(res.headers.get('content-type')).toMatch(/text\/html/)
        const html = await res.text()
        expect(html).toContain('<!DOCTYPE html>')
        expect(html).toContain('Unlock Pro')
        expect(html).toContain('/checkout')       // drives the flow against the same-origin API
        expect(html).toContain('MONETA')          // sovereign attribution
        // No rented processor leaks into the storefront.
        expect(html.toLowerCase()).not.toContain('lemonsqueezy')
        expect(html.toLowerCase()).not.toContain('stripe')
    })

    it('GET /buy is an alias for the checkout page', async () => {
        const res = await request('GET', '/buy')
        expect(res.status).toBe(200)
        expect(res.headers.get('content-type')).toMatch(/text\/html/)
    })

    it('unknown routes 404', async () => {
        const res = await request('GET', '/nope')
        expect(res.status).toBe(404)
    })
})
