"""P-256 signing for the player-issued device nonce. No third-party binaries."""
import hashlib
import os
import base64
P=0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
N=0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G=(0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)

def inverse(value,modulus):
    # Fermat also works on Kodi versions embedding Python before 3.8.
    return pow(value%modulus,modulus-2,modulus)


def add(a,b):
    if a is None:return b
    if b is None:return a
    x,y=a;u,v=b
    if x==u and (y+v)%P==0:return None
    slope=((3*x*x-3)*inverse(2*y,P) if a==b else (v-y)*inverse(u-x,P))%P
    result=(slope*slope-x-u)%P
    return result,(slope*(x-result)-y)%P


def multiply(value):
    point=None;base=G
    while value:
        if value&1:point=add(point,base)
        base=add(base,base);value>>=1
    return point


def random_scalar():
    while True:
        scalar=int.from_bytes(os.urandom(32),'big')
        if 0<scalar<N:return scalar


def b64(value):return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def sign_nonce(nonce):
    private=random_scalar();x,y=multiply(private)
    public={'kty':'EC','crv':'P-256','x':b64(x.to_bytes(32,'big')),'y':b64(y.to_bytes(32,'big')),'ext':True}
    digest=int.from_bytes(hashlib.sha256(nonce.encode('utf-8')).digest(),'big')
    while True:
        ephemeral=random_scalar();r=multiply(ephemeral)[0]%N
        if not r:continue
        s=(inverse(ephemeral,N)*(digest+r*private))%N
        if s:return public,b64(r.to_bytes(32,'big')+s.to_bytes(32,'big'))
