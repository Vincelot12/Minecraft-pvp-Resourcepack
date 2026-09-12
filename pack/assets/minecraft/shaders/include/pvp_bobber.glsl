// Bobber pixels are marked with alpha 249/255 so they can be told apart
// from every other entity drawn by this shader. The band stays narrow so
// genuinely translucent entities are never discarded.
bool pvp_isBobber(float alpha) {
    return alpha > 0.95 && alpha < 1.0;
}

void pvp_hideCloseBobber(float dist, float cutoff, float alpha) {
    if (pvp_isBobber(alpha) && dist < cutoff) {
        discard;
    }
}
