"""Gera o "Pix copia e cola" (BR Code estático) para a página de doação.
Uso: python pix.py <chave> <nome> <cidade>   -> imprime o payload."""
import sys


def crc16(s: str) -> str:
    crc = 0xFFFF  # CRC-16/CCITT-FALSE, o que o Banco Central pede
    for b in s.encode():
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return f"{crc:04X}"


def f(id_, v):
    return f"{id_}{len(v):02d}{v}"


def payload(key, name, city, txid="BIOFUT", msg=""):  # msg: the message the bank shows with the Pix (field 26-02)
    p = (f("00", "01") + f("26", f("00", "br.gov.bcb.pix") + f("01", key) + (f("02", msg) if msg else ""))
         + f("52", "0000") + f("53", "986") + f("58", "BR")
         + f("59", name[:25]) + f("60", city[:15]) + f("62", f("05", txid)) + "6304")
    return p + crc16(p)


if __name__ == "__main__":
    if len(sys.argv) == 4:
        print(payload(*sys.argv[1:]))
    else:
        assert crc16("123456789") == "29B1"  # vetor de teste padrão do CRC-16/CCITT-FALSE
        p = payload("email@exemplo.com", "BIOFUT", "PORTO ALEGRE")
        assert p.startswith("000201") and crc16(p[:-4]) == p[-4:]
        m = payload("email@exemplo.com", "BIOFUT", "PORTO ALEGRE", "APOIE", "Apoio pelo site")
        assert "0215Apoio pelo site" in m and "0505APOIE" in m and crc16(m[:-4]) == m[-4:]
        print("ok", p)
