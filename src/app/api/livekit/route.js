import { NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";

export async function POST(request) {
  try {
    const body = await request.json();
    const roomName = body.roomName || "aula-2getsim";
    const identity = body.identity || "utente-" + Math.random().toString(36).slice(2, 8);
    const participantName = body.participantName || "Partecipante";
    const isMaster = Boolean(body.isMaster);

    const apiKey = process.env.LIVEKIT_API_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET;
    const wsUrl = process.env.LIVEKIT_URL;

    if (!apiKey || !apiSecret || !wsUrl) {
      return NextResponse.json(
        { error: "Variabili LIVEKIT non configurate su Vercel." },
        { status: 500 }
      );
    }

    const token = new AccessToken(apiKey, apiSecret, {
      identity,
      name: participantName,
      ttl: "6h",
    });

    token.addGrant({
      roomJoin: true,
      room: roomName,
      canPublish: isMaster,
      canSubscribe: true,
      canPublishData: true,
    });

    const jwt = await token.toJwt();
    return NextResponse.json({ token: jwt, url: wsUrl });
  } catch (err) {
    return NextResponse.json(
      { error: err.message || "Errore generazione token audio" },
      { status: 500 }
    );
  }
}
