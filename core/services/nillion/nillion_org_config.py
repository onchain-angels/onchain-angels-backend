import os
from decouple import config

config = {
    "org_credentials": {
        "secret_key": config("NILLION_SECRET_KEY"),
        "org_did": config("NILLION_ORG_DID"),
    },
    "nodes": [
        {
            "url": "https://nildb-zy8u.nillion.network",
            "did": "did:nil:testnet:nillion1fnhettvcrsfu8zkd5zms4d820l0ct226c3zy8u",
        },
        {
            "url": "https://nildb-rl5g.nillion.network",
            "did": "did:nil:testnet:nillion14x47xx85de0rg9dqunsdxg8jh82nvkax3jrl5g",
        },
        {
            "url": "https://nildb-lpjp.nillion.network",
            "did": "did:nil:testnet:nillion167pglv9k7m4gj05rwj520a46tulkff332vlpjp",
        },
    ],
}
