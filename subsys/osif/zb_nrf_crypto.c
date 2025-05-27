/*
 * Copyright (c) 2020 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include <zephyr/sys/__assert.h>
#include <zephyr/random/random.h>
#include <zboss_api.h>
#if CONFIG_NRF_SECURITY
#include <psa/crypto.h>
#else
#error No crypto suite for Zigbee stack has been selected
#endif

#include "zb_nrf_crypto.h"

#define ECB_AES_KEY_SIZE   16
#define ECB_AES_BLOCK_SIZE 16

void zb_osif_rng_init(void)
{
}

zb_uint32_t zb_random_seed(void)
{
	zb_uint32_t rnd_val = 0;
	int err_code;

#if defined(CONFIG_ENTROPY_HAS_DRIVER)
	err_code = sys_csrand_get(&rnd_val, sizeof(rnd_val));
#else
#warning Entropy driver required to generate cryptographically secure random numbers
	sys_rand_get(&rnd_val, sizeof(rnd_val));
	err_code = 0;
#endif /* CONFIG_ENTROPY_HAS_DRIVER */
	__ASSERT_NO_MSG(err_code == 0);
	return rnd_val;
}

void psa_init(void)
{
	psa_status_t status = psa_crypto_init();
	ZVUNUSED(status);
	__ASSERT(status == PSA_SUCCESS, "Cannot initialize PSA crypto");
}

void zb_osif_aes_init(void)
{
	psa_init();
}

void zb_osif_aes128_hw_encrypt(const zb_uint8_t *key, const zb_uint8_t *msg, zb_uint8_t *c)
{
	if (!(c && msg && key)) {
		__ASSERT(false, "NULL argument passed");
		return;
	}

	psa_status_t status;
	psa_key_id_t key_id;
	uint32_t out_len;

	ZVUNUSED(status);

	psa_key_attributes_t key_attributes = PSA_KEY_ATTRIBUTES_INIT;
	psa_set_key_usage_flags(&key_attributes, PSA_KEY_USAGE_ENCRYPT | PSA_KEY_USAGE_DECRYPT);
	psa_set_key_lifetime(&key_attributes, PSA_KEY_LIFETIME_VOLATILE);
	psa_set_key_algorithm(&key_attributes, PSA_ALG_ECB_NO_PADDING);
	psa_set_key_type(&key_attributes, PSA_KEY_TYPE_AES);
	psa_set_key_bits(&key_attributes, 128);

	status = psa_import_key(&key_attributes, key, ECB_AES_KEY_SIZE, &key_id);
	__ASSERT(status == PSA_SUCCESS, "psa_import failed! (Error: %d)", status);

	psa_reset_key_attributes(&key_attributes);

	status = psa_cipher_encrypt(key_id, PSA_ALG_ECB_NO_PADDING, msg, ECB_AES_KEY_SIZE, c,
				    ECB_AES_KEY_SIZE, &out_len);
	__ASSERT(status == PSA_SUCCESS, "psa_cipher_encrypt failed! (Error: %d)", status);

	psa_destroy_key(key_id);
}

zb_int_t zb_osif_scalarmult(zb_uint8_t *result_point,
                            const zb_uint8_t *scalar,
                            const zb_uint8_t *point)
{
	psa_status_t status;
	mbedtls_svc_key_id_t key_id;
	size_t output_length;

	ZVUNUSED(status);

	psa_init();

	psa_key_attributes_t key_attributes = PSA_KEY_ATTRIBUTES_INIT;
	psa_set_key_usage_flags(&key_attributes, PSA_KEY_USAGE_DERIVE);
	psa_set_key_lifetime(&key_attributes, PSA_KEY_LIFETIME_VOLATILE);
	psa_set_key_algorithm(&key_attributes, PSA_ALG_ECDH);
	psa_set_key_type(&key_attributes, PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_MONTGOMERY));

	status = psa_import_key(&key_attributes, scalar, ZB_ECC_CURVE25519_BASE_POINT_LEN, &key_id);
	__ASSERT(status == PSA_SUCCESS, "psa_import failed! (Error: %d)", status);

	psa_reset_key_attributes(&key_attributes);

	status = psa_raw_key_agreement(PSA_ALG_ECDH, key_id, point, ZB_ECC_CURVE25519_BASE_POINT_LEN,
			 result_point, ZB_ECC_SECRET_MAX_LEN, &output_length);
	__ASSERT(status == PSA_SUCCESS, "psa_raw_key_agreement failed! (Error: %d)", status);

	psa_destroy_key(key_id);

	return 0;
}


zb_ret_t zb_hw_ccm_encrypt_n_auth_raw(zb_uint8_t *key,
									  const zb_uint8_t *nonce,
									  const zb_uint8_t *string_a,
									  zb_uint32_t string_a_len,
									  const zb_uint8_t *string_m,
									  zb_uint32_t string_m_len,
									  zb_uint8_t *dest_buf,
									  zb_uint16_t dest_len)
{
	psa_status_t status;
	psa_key_id_t key_id;
	psa_key_attributes_t key_attributes = PSA_KEY_ATTRIBUTES_INIT;
	size_t output_length = 0;

	if (!key || !nonce || !string_m || !dest_buf) {
		return RET_ERROR;
	}

	psa_init();

	psa_set_key_usage_flags(&key_attributes, PSA_KEY_USAGE_ENCRYPT);
	psa_set_key_lifetime(&key_attributes, PSA_KEY_LIFETIME_VOLATILE);
	psa_set_key_algorithm(&key_attributes, PSA_ALG_CCM);
	psa_set_key_type(&key_attributes, PSA_KEY_TYPE_AES);
	psa_set_key_bits(&key_attributes, 128);

	status = psa_import_key(&key_attributes, key, 16, &key_id);
	if (status != PSA_SUCCESS) {
		return RET_ERROR;
	}

	psa_reset_key_attributes(&key_attributes);

	status = psa_aead_encrypt(
		key_id,
		PSA_ALG_CCM,
		nonce, 13, // Zigbee uses 13-byte nonce
		string_a, string_a_len, // AAD
		string_m, string_m_len,
		dest_buf, dest_len,
		&output_length
	);

	psa_destroy_key(key_id);

	if (status == PSA_SUCCESS) {
		// output_length is the total length (ciphertext + tag)
		return RET_OK;
	} else {
		return RET_ERROR;
	}
}

zb_ret_t zb_osif_ccm_decrypt_n_auth_raw(zb_uint8_t *key,
										const zb_uint8_t *nonce,
										const zb_uint8_t *string_a,
										zb_uint32_t string_a_len,
										const zb_uint8_t *string_c_u,
										zb_uint16_t string_c_u_len,
										zb_uint8_t *string_dest,
										zb_uint16_t *string_dest_len)
{
	psa_status_t status;
	psa_key_id_t key_id;
	psa_key_attributes_t key_attributes = PSA_KEY_ATTRIBUTES_INIT;
	size_t output_length = 0;
	size_t tag_length = 4; // Zigbee CCM* uses 4-byte MIC/tag
	size_t ciphertext_length;

	if (!key || !nonce || !string_c_u || !string_dest || !string_dest_len) {
		return RET_ERROR;
	}

	if (string_c_u_len < tag_length) {
		*string_dest_len = 0;
		return RET_ERROR;
	}

	ciphertext_length = string_c_u_len - tag_length;

	psa_init();

	psa_set_key_usage_flags(&key_attributes, PSA_KEY_USAGE_DECRYPT);
	psa_set_key_lifetime(&key_attributes, PSA_KEY_LIFETIME_VOLATILE);
	psa_set_key_algorithm(&key_attributes, PSA_ALG_CCM);
	psa_set_key_type(&key_attributes, PSA_KEY_TYPE_AES);
	psa_set_key_bits(&key_attributes, 128);

	status = psa_import_key(&key_attributes, key, 16, &key_id);
	if (status != PSA_SUCCESS) {
		*string_dest_len = 0;
		return RET_ERROR;
	}

	psa_reset_key_attributes(&key_attributes);

	status = psa_aead_decrypt(
		key_id,
		PSA_ALG_CCM,
		nonce, 13, // Zigbee uses 13-byte nonce
		string_a, string_a_len, // AAD
		string_c_u, string_c_u_len, // ciphertext + tag
		string_dest, string_dest_len ? *string_dest_len : 0,
		&output_length
	);

	psa_destroy_key(key_id);

	if (status == PSA_SUCCESS) {
		*string_dest_len = (zb_uint16_t)output_length;
		return RET_OK;
	} else {
		*string_dest_len = 0;
		return RET_ERROR;
	}
}
