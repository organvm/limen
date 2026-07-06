import type { IncomingMessage, ServerResponse } from 'node:http'
import { Readable } from 'node:stream'
import { beforeAll, describe, expect, it } from 'vitest'
import { createRequestListener } from '../server'
import { MintService } from '../service'
import { loadConfigFromEnv } from '../config'
import { generateMintKeypair, importSigningKey } from '../keys'

let publicJwk: JsonWebKey
let requestMint: (method: string, path: string, body?: unknown) => Promise<TestResponse>

interface TestResponse {
    status: number
    headers: { get: (name: string) => string | null }
    json: () => Promise<unknown>
    text: () => Promise<string>
}

function testRequest(method: string, path: string, body?: unknown): IncomingMessage {
    const payload = body === undefined ? [] : [Buffer.from(JSON.stringify(body))]
    const req = Readable.from(payload) as IncomingMessage
    req.method = method
    req.url = path
    return req
}

async function dispatch(
    listener: (req: IncomingMessage, res: ServerResponse) => Promise<void>,
    method: string,
    path: string,
    body?: unknown,
): Promise<TestResponse> {
    const headers = new Map<string, string>()
    let responseBody = ''
    let resolveEnd: () => void = () => {}
    const ended = new Promise<void>(resolve => {
        resolveEnd = resolve
    })
    const response = {
        statusCode: 200,
        setHeader(name: string, value: number | string | readonly string[]): void {
            headers.set(name.toLowerCase(), String(value))
        },
        end(chunk?: string | Buffer): void {
            if (chunk !== undefined) responseBody += Buffer.isBuffer(chunk) ? chunk.toString('utf8') : String(chunk)
            resolveEnd()
        },
    } as ServerResponse

    await listener(testRequest(method, path, body), response)
    await ended

    return {
        status: response.statusCode,
        headers: { get: (name: string) => headers.get(name.toLowerCase()) ?? null },
        json: async () => JSON.parse(responseBody),
        text: async () => responseBody,
    }
}

beforeAll(async () => {
    const keypair = await generateMintKeypair()
    publicJwk = keypair.publicJwk
    const config = loadConfigFromEnv({ MINT_PRIVATE_JWK: JSON.stringify(keypair.privateJwk) }) // no address -> unconfigured
    const service = new MintService({ config, signingKey: await importSigningKey(keypair.privateJwk) })
    const listener = createRequestListener({ service, publicJwk: keypair.publicJwk })
    requestMint = (method, path, body) => dispatch(listener, method, path, body)
})

describe('mint HTTP server', () => {
    it('GET /health reports liveness + configured flag + pooled demand', async () => {
        const res = await requestMint('GET', '/health')
        expect(res.status).toBe(200)
        expect(await res.json()).toEqual({ ok: true, configured: false, waiting: 0 })
    })

    it('GET /pubkey serves the verify key for the product build', async () => {
        const res = await requestMint('GET', '/pubkey')
        expect(res.status).toBe(200)
        const body = await res.json() as { jwk: JsonWebKey }
        expect(body.jwk.x).toBe(publicJwk.x)
        expect(body.jwk.d).toBeUndefined()
    })

    it('POST /checkout pools demand (reserves) while unconfigured', async () => {
        const res = await requestMint('POST', '/checkout', { email: 'a@b.com' })
        expect(res.status).toBe(202)
        expect(((await res.json()) as { status: string }).status).toBe('reserved')
    })

    it('GET / serves the self-contained checkout page (no third-party checkout)', async () => {
        const res = await requestMint('GET', '/')
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
        const res = await requestMint('GET', '/buy')
        expect(res.status).toBe(200)
        expect(res.headers.get('content-type')).toMatch(/text\/html/)
    })

    it('unknown routes 404', async () => {
        const res = await requestMint('GET', '/nope')
        expect(res.status).toBe(404)
    })
})
