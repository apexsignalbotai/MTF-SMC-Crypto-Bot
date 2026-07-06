import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_KEY = import.meta.env.VITE_SUPABASE_KEY

let supabase = null

if (SUPABASE_URL && SUPABASE_KEY) {
  try {
    supabase = createClient(SUPABASE_URL, SUPABASE_KEY)
  } catch (error) {
    console.error("Error creating Supabase client in React:", error)
  }
} else {
  console.warn("WARNING: Supabase URL or Key missing in Frontend environment variables.")
}

export { supabase }
